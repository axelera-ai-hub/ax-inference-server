
// gRPC front end for the pipeline inference service.
// Implements Ax::GrpcServer: decodes incoming images, feeds them to the pipeline built by
// PipelineBuilder, converts results to protobuf responses, and handles restart, watchdog,
// statistics and shutdown.
#include "interface/grpc.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <errno.h>
#include <filesystem>
#include <fstream>
#include <functional>
#include <future>
#include <iomanip>
#include <map>
#include <memory>
#include <mutex>
#include <queue>
#include <sstream>
#include <stack>
#include <string>
#include <sys/types.h>
#include <thread>
#include <unistd.h>
#include <unordered_map>
#include <vector>

#include <gperftools/malloc_extension.h>

#include "AxInferenceNet.hpp"
#include "AxMetaObjectDetection.hpp"
#include "AxMetaKptsDetection.hpp"
#include "AxMetaSegmentsDetection.hpp"
#include "axruntime/axruntime.hpp"
#include "opencv2/opencv.hpp"

#include <grpcpp/grpcpp.h>
#include <grpcpp/resource_quota.h>

#include "AxMetaClassification.hpp"

#include "axinfer/v1/inference.grpc.pb.h"
#include "axinfer/v1/inference.pb.h"

#include "common/io_uring_logger.hpp"
#include "decoders/decoder_factory.hpp"
#include "AxVideoBuffer.hpp"
#include "pipeline/frame.h"
#include "pipeline/node.h"
#include "pipeline/timed_queue_push.h"
#include "pipeline/builder.h"

using grpc::Server;
using grpc::ServerBuilder;
using grpc::ServerContext;
using grpc::ServerWriter;
using grpc::Status;

using namespace std::string_literals;
using std::chrono::high_resolution_clock;
using std::chrono::microseconds;

// Log helpers that forward to the IoUringLogger singleton.
#define GRPC_LOG(category, msg)           IoUringLogger::instance().log(category, msg)
#define GRPC_LOGF(category, fmt, ...)     IoUringLogger::instance().logf(category, fmt, ##__VA_ARGS__)
// Unused in this file.
#define SAFE_STR(s)                       ((s) ? (s) : "(null)")

namespace {

/**
 * Print a message to stdout and write it to the log.
 *
 * Args:
 *   msg (const std::string&): Message text, including any trailing newline.
 *   category (const char*, optional): Log category. Defaults to "STARTUP".
 */
void print_and_log(const std::string &msg, const char *category = "STARTUP") {
    std::cout << msg;
    IoUringLogger::instance().log(category, msg);
}

/**
 * Print a printf-formatted message (up to 4096 bytes) to stdout and write it to the log.
 *
 * Args:
 *   category (const char*): Log category.
 *   format (const char*): printf-style format string.
 *   args: Values for the format conversions.
 */
template <typename... Args>
void printf_and_log(const char *category, const char *format, Args... args) {
    char buffer[4096];
    snprintf(buffer, sizeof(buffer), format, args...);
    std::cout << buffer;
    IoUringLogger::instance().log(category, buffer);
}

}


namespace {

// Source of unique frame ids for requests.
static std::atomic<int> g_frame_id{0};

/** Pixel format of frames handed to the pipeline; mirrors GrpcServerConfig::output_format. */
enum class OutputFormat { BGR, I420, RGBA };


// Capacity reserved for each request's encoded image buffer.
constexpr size_t MAX_EXPECTED_IMAGE_SIZE = 50 * 1024 * 1024;

using Frame = Ax::Frame;

// Unused in this file.
constexpr int NUM_SHARDS = 31;

namespace {

/**
 * Append the keypoints of one detection to a protobuf Detection.
 *
 * The keypoint count comes from the meta shape, defaulting to 17 when the shape is empty.
 *
 * Args:
 *   kd (AxMetaKptsDetection*): Keypoint meta.
 *   idx (size_t): Element within kd to emit.
 *   d (axinfer::v1::Detection*): Detection to append to.
 *   offset_x (float): Added to every x coordinate.
 *   offset_y (float): Added to every y coordinate.
 */
void emit_keypoints(AxMetaKptsDetection *kd, size_t idx, axinfer::v1::Detection *d,
                    float offset_x, float offset_y)
{
    const auto kshape = kd->get_kpts_shape();
    const size_t n_kpts = kshape.empty() ? 17u : static_cast<size_t>(kshape[0]);
    if (n_kpts == 0) return;
    auto kpts = kd->get_kpts_xyv(idx, n_kpts);
    for (const auto &kpt : kpts) {
        auto *pt = d->add_keypoints();
        pt->set_x(static_cast<float>(kpt.x) + offset_x);
        pt->set_y(static_cast<float>(kpt.y) + offset_y);
        pt->set_confidence(kpt.visibility);
    }
}

/**
 * Fill the face box and landmarks of a Detection from the best-scoring element of a keypoint meta.
 *
 * The landmark count comes from the meta shape, defaulting to 5 when the shape is empty.
 * Does nothing if the meta is empty.
 *
 * Args:
 *   kd (AxMetaKptsDetection*): Keypoint meta.
 *   d (axinfer::v1::Detection*): Detection to fill.
 *   offset_x (float): Added to the box origin and to every landmark x.
 *   offset_y (float): Added to the box origin and to every landmark y.
 */
void emit_face(AxMetaKptsDetection *kd, axinfer::v1::Detection *d,
               float offset_x, float offset_y)
{
    if (kd->num_elements() == 0) return;
    size_t best = 0;
    for (size_t i = 1; i < kd->num_elements(); ++i)
        if (kd->score(i) > kd->score(best)) best = i;

    auto box = kd->get_box_xyxy(best);
    auto *bbox = d->mutable_face_bbox();
    bbox->set_x(static_cast<uint32_t>(box.x1 + offset_x));
    bbox->set_y(static_cast<uint32_t>(box.y1 + offset_y));
    bbox->set_w(static_cast<uint32_t>(box.x2 - box.x1));
    bbox->set_h(static_cast<uint32_t>(box.y2 - box.y1));

    const auto kshape = kd->get_kpts_shape();
    const size_t n_kpts = kshape.empty() ? 5u : static_cast<size_t>(kshape[0]);
    if (n_kpts == 0) return;
    try {
        auto kpts = kd->get_kpts_xyv(best, n_kpts);
        for (const auto &kpt : kpts) {
            auto *pt = d->add_face_landmarks();
            pt->set_x(static_cast<float>(kpt.x) + offset_x);
            pt->set_y(static_cast<float>(kpt.y) + offset_y);
            pt->set_confidence(kpt.visibility);
        }
    } catch (const std::out_of_range &) {}
}

/**
 * Append the first embedding vector of a meta to a Detection under the given key.
 *
 * Args:
 *   ed (AxMetaEmbeddings*): Embedding meta.
 *   key (const std::string&): Name stored with the embedding.
 *   d (axinfer::v1::Detection*): Detection to append to.
 */
void emit_named_embedding(AxMetaEmbeddings *ed, const std::string &key, axinfer::v1::Detection *d)
{
    auto embeddings = ed->get_embeddings();
    if (embeddings.empty()) return;
    auto *ne = d->add_embeddings();
    ne->set_key(key);
    for (float v : embeddings[0]) ne->add_vector(v);
}

/**
 * Append a simplified outline of one segment mask to a Detection.
 *
 * The mask is thresholded at 127, the longest external contour is simplified with
 * cv::approxPolyDP (epsilon 2.0), and its points are mapped from mask coordinates back to
 * image coordinates. The mapping assumes a 640x640 letterboxed model input and a mask
 * stride of 4. Nothing is emitted when the mask is empty or inconsistent, and any exception
 * is swallowed.
 *
 * Args:
 *   sd (AxMetaSegmentsDetection*): Segment meta.
 *   idx (size_t): Element within sd to emit.
 *   d (axinfer::v1::Detection*): Detection to append to.
 *   offset_x (float): Added to every output x coordinate.
 *   offset_y (float): Added to every output y coordinate.
 */
void emit_segmentation_polygon(AxMetaSegmentsDetection *sd, size_t idx, axinfer::v1::Detection *d,
                                float offset_x, float offset_y)
{
    try {
        auto seg = sd->get_segment(idx);
        int sw = seg.x2 - seg.x1;
        int sh = seg.y2 - seg.y1;
        if (sw <= 0 || sh <= 0 || seg.map.size() != static_cast<size_t>(sw * sh)) return;

        cv::Mat mask(sh, sw, CV_8U, const_cast<uint8_t *>(seg.map.data()));
        cv::Mat binary;
        cv::threshold(mask, binary, 127, 255, cv::THRESH_BINARY);
        std::vector<std::vector<cv::Point>> contours;
        cv::findContours(binary, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_TC89_L1);
        if (contours.empty()) return;

        size_t best = 0;
        for (size_t c = 1; c < contours.size(); ++c)
            if (contours[c].size() > contours[best].size()) best = c;
        std::vector<cv::Point> approx;
        cv::approxPolyDP(contours[best], approx, 2.0, true);

        constexpr float model_sz   = 640.0f;
        constexpr float proto_scale = 4.0f;
        float img_w = static_cast<float>(seg.base_box_x2 + 1);
        float img_h = static_cast<float>(seg.base_box_y2 + 1);
        float ls    = std::min(model_sz / img_w, model_sz / img_h);
        float pad_x = (model_sz - img_w * ls) / 2.0f;
        float pad_y = (model_sz - img_h * ls) / 2.0f;

        for (const auto &pt : approx) {
            float px = static_cast<float>(pt.x + seg.x1) * proto_scale;
            float py = static_cast<float>(pt.y + seg.y1) * proto_scale;
            auto *p = d->add_segmentation();
            p->set_x((px - pad_x) / ls + offset_x);
            p->set_y((py - pad_y) / ls + offset_y);
        }
    } catch (...) {}
}

/**
 * Convert a frame's meta results into a FrameResult protobuf.
 *
 * Detections come from the first object detection found in the meta. For each one, entries
 * whose key ends in "_<index>" (written by RoiCollectNode) are attached as classifications,
 * keypoints or face data (per meta_key_roles), embeddings, or a segmentation outline, with
 * coordinates offset by the ROI crop origin when known, otherwise by the detection box
 * origin. A top-level "classifications" meta becomes frame-level classifications. If there
 * is no object detection, detections are built from the first keypoint meta and from the
 * first segment meta, each only when non-empty.
 *
 * Args:
 *   meta (const Ax::MetaMap&): Result meta of the frame.
 *   labels (const std::vector<std::string>&): Class names indexed by class id.
 *   resp (axinfer::v1::FrameResult*): Response to fill.
 *   pipeline_ext (const Ax::FramePipelineExt*, optional): Provides ROI crop rectangles.
 *   meta_key_roles (const std::unordered_map<std::string, std::string>&, optional): Maps a
 *     meta key prefix to "keypoints" or "face". Unlisted keys count as "keypoints".
 */
inline void fill_response(const Ax::MetaMap &meta,
                          const std::vector<std::string> &labels,
                          axinfer::v1::FrameResult *resp,
                          const Ax::FramePipelineExt *pipeline_ext = nullptr,
                          const std::unordered_map<std::string, std::string> &meta_key_roles = {})
{
    auto dit = meta.end();
    for (auto it = meta.begin(); it != meta.end(); ++it) {
        if (dynamic_cast<AxMetaObjDetection *>(it->second.get())) {
            dit = it;
            break;
        }
    }
    if (dit != meta.end()) {
        auto *det = dynamic_cast<AxMetaObjDetection *>(dit->second.get());
        if (det) {
            for (size_t i = 0; i < det->num_elements(); ++i) {
                auto box = det->get_box_xyxy(i);
                auto id  = det->class_id(i);
                auto *d  = resp->add_detections();
                d->set_class_id(id >= 0 ? static_cast<uint32_t>(id) : 0u);
                d->set_label(id >= 0 && id < (int)labels.size() ? labels[id] : "");
                d->set_score(det->score(i));
                auto *bbox = d->mutable_bbox();
                bbox->set_x(static_cast<uint32_t>(box.x1));
                bbox->set_y(static_cast<uint32_t>(box.y1));
                bbox->set_w(static_cast<uint32_t>(box.x2 - box.x1));
                bbox->set_h(static_cast<uint32_t>(box.y2 - box.y1));

                float offset_x = static_cast<float>(box.x1);
                float offset_y = static_cast<float>(box.y1);
                if (pipeline_ext) {
                    auto rect_it = pipeline_ext->roi_crop_rects.find(static_cast<int>(i));
                    if (rect_it != pipeline_ext->roi_crop_rects.end()) {
                        offset_x = static_cast<float>(rect_it->second.x);
                        offset_y = static_cast<float>(rect_it->second.y);
                    }
                }

                {
                    const std::string suffix = "_" + std::to_string(i);
                    for (const auto &[key, val] : meta) {
                        if (key.size() <= suffix.size()) continue;
                        if (key.compare(key.size() - suffix.size(), suffix.size(), suffix) != 0)
                            continue;
                        const std::string prefix = key.substr(0, key.size() - suffix.size());

                        if (auto *cls = dynamic_cast<AxMetaClassification *>(val.get())) {
                            if (cls->get_number_of_subframes() > 0) {
                                const auto &sc = cls->get_scores();
                                const auto &cl = cls->get_classes();
                                const auto &lb = cls->get_labels();
                                for (size_t j = 0; j < sc[0].size(); ++j) {
                                    auto *cs = d->add_classifications();
                                    cs->set_class_id(static_cast<uint32_t>(cl[0][j]));
                                    cs->set_label(lb[0][j]);
                                    cs->set_score(sc[0][j]);
                                }
                            }
                            continue;
                        }
                        if (auto *kd = dynamic_cast<AxMetaKptsDetection *>(val.get())) {
                            auto role_it = meta_key_roles.find(prefix);
                            const std::string &role =
                                role_it != meta_key_roles.end() ? role_it->second : "keypoints";
                            if (role == "face") {
                                emit_face(kd, d, offset_x, offset_y);
                            } else if (kd->num_elements() > 0) {
                                emit_keypoints(kd, 0, d, offset_x, offset_y);
                            }
                            continue;
                        }
                        if (auto *ed = dynamic_cast<AxMetaEmbeddings *>(val.get())) {
                            emit_named_embedding(ed, prefix, d);
                            continue;
                        }
                        if (auto *sd = dynamic_cast<AxMetaSegmentsDetection *>(val.get())) {
                            if (sd->num_elements() > 0) {
                                emit_segmentation_polygon(sd, 0, d, offset_x, offset_y);
                            }
                            continue;
                        }
                    }
                }
            }
        }
    }

    auto cit = meta.find("classifications");
    if (cit != meta.end()) {
        auto *cls = dynamic_cast<AxMetaClassification *>(cit->second.get());
        if (cls && !cls->get_scores().empty()) {
            const auto &scores  = cls->get_scores();
            const auto &classes = cls->get_classes();
            const auto &lbls    = cls->get_labels();
            for (size_t j = 0; j < scores[0].size(); ++j) {
                auto *cs = resp->add_classifications();
                cs->set_class_id(static_cast<uint32_t>(classes[0][j]));
                cs->set_label(lbls[0][j]);
                cs->set_score(scores[0][j]);
            }
        }
    }

    if (dit == meta.end()) {
        for (const auto &[key, meta_ptr] : meta) {
            auto *kd = dynamic_cast<AxMetaKptsDetection *>(meta_ptr.get());
            if (!kd || kd->num_elements() == 0) continue;

            for (size_t i = 0; i < kd->num_elements(); ++i) {
                auto box = kd->get_box_xyxy(i);
                auto *d  = resp->add_detections();
                d->set_class_id(0u);
                d->set_label(!labels.empty() ? labels[0] : "");
                d->set_score(kd->score(i));
                auto *bbox = d->mutable_bbox();
                bbox->set_x(static_cast<uint32_t>(std::max(0, box.x1)));
                bbox->set_y(static_cast<uint32_t>(std::max(0, box.y1)));
                bbox->set_w(static_cast<uint32_t>(std::max(0, box.x2 - box.x1)));
                bbox->set_h(static_cast<uint32_t>(std::max(0, box.y2 - box.y1)));
                emit_keypoints(kd, i, d, 0.0f, 0.0f);
            }
            break;
        }
    }

    if (dit == meta.end()) {
    for (const auto &[key, meta_ptr] : meta) {
        auto *sd = dynamic_cast<AxMetaSegmentsDetection *>(meta_ptr.get());
        if (!sd || sd->num_elements() == 0) continue;

        for (size_t i = 0; i < sd->num_elements(); ++i) {
            auto box = sd->get_box_xyxy(i);
            auto id  = sd->class_id(i);
            auto *d  = resp->add_detections();
            d->set_class_id(id >= 0 ? static_cast<uint32_t>(id) : 0u);
            d->set_label(id >= 0 && id < static_cast<int>(labels.size())
                         ? labels[id] : "");
            d->set_score(sd->score(i));
            auto *bbox = d->mutable_bbox();
            bbox->set_x(static_cast<uint32_t>(std::max(0, box.x1)));
            bbox->set_y(static_cast<uint32_t>(std::max(0, box.y1)));
            bbox->set_w(static_cast<uint32_t>(std::max(0, box.x2 - box.x1)));
            bbox->set_h(static_cast<uint32_t>(std::max(0, box.y2 - box.y1)));
            emit_segmentation_polygon(sd, i, d, 0.0f, 0.0f);
        }
        break;
    }
    }
}

}

/** Lifecycle of the service: requests are accepted only in READY. */
enum class ServerState { INITIALIZING, READY, SHUTTING_DOWN, STOPPED };

/**
 * Pool of reusable Frame objects.
 *
 * acquire() hands out a shared_ptr whose deleter returns the frame to the pool, so frames
 * (and the buffers they hold) are recycled across requests. If the pool is empty a new frame
 * is allocated.
 *
 * Note:
 *   Thread-safe. Frames still in use keep the pool alive through the deleter.
 */
class FramePool : public std::enable_shared_from_this<FramePool> {
public:
    /** Create the pool with pool_size preallocated frames. */
    explicit FramePool(size_t pool_size) {
        for (size_t i = 0; i < pool_size; ++i) pool_.push(new Frame());
    }
    /** Free all frames currently held by the pool. */
    ~FramePool() {
        std::lock_guard<std::mutex> lock(mutex_);
        while (!pool_.empty()) { delete pool_.top(); pool_.pop(); }
    }
    /**
     * Take a frame from the pool and reset its per-request fields.
     *
     * Returns:
     *   std::shared_ptr<Frame>: A frame that returns to the pool when the last reference ends.
     */
    std::shared_ptr<Frame> acquire() {
        std::lock_guard<std::mutex> lock(mutex_);
        Frame *f = nullptr;
        if (pool_.empty()) {
            GRPC_LOG("POOL", "FramePool exhausted, allocating new frame\n");
            f = new Frame();
        } else {
            f = pool_.top();
            pool_.pop();
        }
        f->meta.clear();
        f->id = 0;
        f->is_dummy = false;
        f->encoded.reset();
        f->net_idx = -1;
        f->start_time = std::chrono::high_resolution_clock::time_point();
        f->end_time   = std::chrono::high_resolution_clock::time_point();
        f->dropped = false;
        f->drop_reason.clear();
        auto self = shared_from_this();
        return std::shared_ptr<Frame>(f, [self](Frame *ptr) { self->release(ptr); });
    }
private:
    /** Return a frame to the pool. */
    void release(Frame *f) {
        std::lock_guard<std::mutex> lock(mutex_);
        pool_.push(f);
    }
    std::stack<Frame *> pool_;
    std::mutex mutex_;
};

/** Return the steady clock time in microseconds. */
inline int64_t steady_now_us() {
    return std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}

/**
 * Implementation of the AxInference gRPC service on top of a built pipeline.
 *
 * Infer() decodes the request image on a worker thread pool, passes the frame to the
 * pipeline entry node, and waits for the output worker to resolve the request's promise
 * with the finished frame. It also tracks statistics and runs optional watchdog and
 * periodic statistics threads.
 *
 * Note:
 *   Call StartWorkers() before serving and SetReady() once the gRPC server is listening.
 *   Shut down with StopInputs(), WaitForPipelineDrain(), then StopOutputs(). The labels
 *   vector is held by reference and must outlive the service.
 */
class PipelineService final : public axinfer::v1::AxInference::Service {
public:
    /**
     * Create the service and start the statistics thread (and the watchdog if enabled).
     *
     * Args:
     *   entry_node (std::shared_ptr<Ax::AxPipelineNode>): Node that receives decoded frames.
     *   result_queue (std::shared_ptr<Ax::BlockingQueue<std::shared_ptr<Frame>>>): Queue the
     *     pipeline's sink writes finished frames to.
     *   all_nodes (std::vector<std::shared_ptr<Ax::AxPipelineNode>>): Every node, in build order,
     *     used for shutdown and queue statistics.
     *   labels (const std::vector<std::string>&): Class names; stored by reference.
     *   timeout_s (int): Seconds Infer() waits for a result.
     *   imdecode_threads (int): Number of decode workers.
     *   frame_pool (std::shared_ptr<FramePool>): Source of frames.
     *   output_format (OutputFormat): Pixel format fed to the pipeline.
     *   watchdog_timeout_ms (int, optional): Watchdog threshold; 0 disables it.
     *   on_watchdog_trigger (std::function<void()>, optional): Called when the watchdog fires.
     *   imdecode_queue_timeout_ms (int, optional): Wait for space in the decode queue.
     *   imdecode_queue_depth (int, optional): Capacity of the decode queue.
     *   meta_key_roles (const std::unordered_map<std::string, std::string>&, optional): Passed
     *     to fill_response().
     */
    PipelineService(
        std::shared_ptr<Ax::AxPipelineNode> entry_node,
        std::shared_ptr<Ax::BlockingQueue<std::shared_ptr<Frame>>> result_queue,
        std::vector<std::shared_ptr<Ax::AxPipelineNode>> all_nodes,
        const std::vector<std::string> &labels,
        int timeout_s,
        int imdecode_threads,
        std::shared_ptr<FramePool> frame_pool,
        OutputFormat output_format,
        int watchdog_timeout_ms = 0,
        std::function<void()> on_watchdog_trigger = nullptr,
        int imdecode_queue_timeout_ms = 2000,
        int imdecode_queue_depth = 1,
        const std::unordered_map<std::string, std::string> &meta_key_roles = {})
        : entry_node_(std::move(entry_node))
        , result_queue_(std::move(result_queue))
        , all_nodes_(std::move(all_nodes))
        , labels_(labels)
        , meta_key_roles_(meta_key_roles)
        , timeout_sec_(timeout_s)
        , imdecode_threads_count_(imdecode_threads)
        , imdecode_queue_timeout_(imdecode_queue_timeout_ms)
        , frame_pool_(std::move(frame_pool))
        , output_format_(output_format)
        , enable_i420_output_(output_format == OutputFormat::I420)
        , imdecode_queue_(imdecode_queue_depth)
        , watchdog_timeout_ms_(watchdog_timeout_ms)
        , on_watchdog_trigger_(std::move(on_watchdog_trigger))
    {
        frame_stats_ = std::make_unique<FrameStats>();
        GRPC_LOG("PIPELINE", "PipelineService constructed\n");
        if (watchdog_timeout_ms_ > 0) {
            GRPC_LOGF("WATCHDOG", "Health watchdog armed: %dms with no successful "
                      "completion despite requests attempted triggers a restart\n",
                      watchdog_timeout_ms_);
            watchdog_thread_ = std::thread([this] { watchdog_loop(); });
        }
        stats_thread_ = std::thread([this] { stats_loop(); });
    }

    /** Stop workers, the watchdog and the statistics thread if still running. */
    ~PipelineService() {
        if (input_running_.load(std::memory_order_acquire) ||
            output_running_.load(std::memory_order_acquire)) {
            server_state_.store(ServerState::SHUTTING_DOWN, std::memory_order_release);
            state_cv_.notify_all();
            StopInputs();
            StopOutputs();
        }
        stop_watchdog();
        stop_stats_thread();
    }

    /** Return true when the service accepts requests. */
    bool IsReady() const {
        return server_state_.load(std::memory_order_acquire) == ServerState::READY;
    }

    /** Move the service to READY and wake the workers waiting to start. */
    void SetReady() {
        GRPC_LOG("PIPELINE", "Transitioning server state: INITIALIZING → READY\n");
        server_state_.store(ServerState::READY, std::memory_order_release);
        state_cv_.notify_all();
    }

    /**
     * Handle one inference request.
     *
     * Decodes the image through the pipeline and fills the response. A request is answered with
     * status DROPPED (gRPC OK) when the decode queue is full or the pipeline dropped the frame.
     *
     * Args:
     *   request (const axinfer::v1::InferRequest*): Request with the encoded image.
     *   response (axinfer::v1::FrameResult*): Filled with the result; request_id is echoed.
     *
     * Returns:
     *   Status: OK on completion or drop, UNAVAILABLE if the server is not READY,
     *     DEADLINE_EXCEEDED if no result arrives within the timeout, INTERNAL on a pipeline or
     *     decode error.
     */
    Status Infer(ServerContext *,
                 const axinfer::v1::InferRequest *request,
                 axinfer::v1::FrameResult *response) override
    {
        auto state = server_state_.load(std::memory_order_acquire);
        if (state != ServerState::READY) {
            const char *s = (state == ServerState::INITIALIZING) ? "INITIALIZING" :
                            (state == ServerState::SHUTTING_DOWN) ? "SHUTTING_DOWN" : "STOPPED";
            return Status(grpc::StatusCode::UNAVAILABLE,
                          std::string("Server is ") + s + ", please retry");
        }

        frame_stats_->requests_since_last_success.fetch_add(1, std::memory_order_relaxed);

        auto frame = frame_pool_->acquire();
        int frame_id = g_frame_id.fetch_add(1, std::memory_order_relaxed);
        frame->id = frame_id;
        frame->start_time = std::chrono::high_resolution_clock::now();
        frame->pipeline_ext = std::make_shared<Ax::FramePipelineExt>();

        auto encoded_vec = std::make_shared<std::vector<uint8_t>>();
        encoded_vec->reserve(MAX_EXPECTED_IMAGE_SIZE);
        encoded_vec->assign(request->image_data().begin(), request->image_data().end());
        frame->encoded = std::move(encoded_vec);

        auto promise = std::make_shared<std::promise<std::shared_ptr<Frame>>>();
        auto fut = promise->get_future();

        {
            std::lock_guard<std::mutex> lk(pending_mutex_);
            pending_[frame_id] = promise;
        }

        if (!try_push_for(imdecode_queue_, frame, imdecode_queue_timeout_)) {
            {
                std::lock_guard<std::mutex> lk(pending_mutex_);
                pending_.erase(frame_id);
            }
            frame_stats_->dropped_frames.fetch_add(1, std::memory_order_relaxed);
            GRPC_LOGF("PIPELINE",
                "imdecode_queue_ full after %ldms, dropping frame %d\n",
                static_cast<long>(imdecode_queue_timeout_.count()), frame_id);
            if (request->has_request_id())
                response->set_request_id(request->request_id());
            response->set_status(axinfer::v1::InferenceStatus::DROPPED);
            response->set_status_message("imdecode_queue_ full");
            return Status::OK;
        }

        auto status = fut.wait_for(std::chrono::seconds(timeout_sec_));
        if (status != std::future_status::ready) {
            std::lock_guard<std::mutex> lk(pending_mutex_);
            pending_.erase(frame_id);
            return Status(grpc::StatusCode::DEADLINE_EXCEEDED,
                          "Timeout waiting for pipeline result");
        }

        try {
            auto result = fut.get();
            if (request->has_request_id())
                response->set_request_id(request->request_id());
            if (result->dropped) {
                response->set_status(axinfer::v1::InferenceStatus::DROPPED);
                response->set_status_message(result->drop_reason);
                return Status::OK;
            }
            fill_response(result->meta, labels_, response, result->pipeline_ext.get(), meta_key_roles_);
            response->set_status(axinfer::v1::InferenceStatus::COMPLETE);
        } catch (const std::exception &e) {
            return Status(grpc::StatusCode::INTERNAL,
                          std::string("Pipeline error: ") + e.what());
        }
        return Status::OK;
    }

    /**
     * Start the decode worker threads and the output worker thread.
     *
     * All workers wait until the service is READY. Each decode worker creates its own decoder,
     * decodes frames from the decode queue and hands them to the entry node; a decode failure
     * is delivered to the waiting request as an exception. The output worker takes finished
     * frames from the result queue, updates statistics and resolves the request promise.
     */
    void StartWorkers() {
        GRPC_LOGF("PIPELINE", "StartWorkers: starting %d imdecode + 1 output\n",
                  imdecode_threads_count_);

        for (int i = 0; i < imdecode_threads_count_; ++i) {
            imdecode_workers_.emplace_back([this, i]() {
                {
                    std::unique_lock<std::mutex> lk(state_mutex_);
                    state_cv_.wait(lk, [this] {
                        auto s = server_state_.load(std::memory_order_acquire);
                        return s == ServerState::READY || s == ServerState::SHUTTING_DOWN;
                    });
                    if (server_state_.load() == ServerState::SHUTTING_DOWN) return;
                }
                auto decoder = DecoderFactory::create_decoder();
                GRPC_LOGF("DECODE_WORKER", "Pipeline decode thread %d using: %s\n",
                          i, decoder->name());

                while (input_running_) {
                    auto frame = imdecode_queue_.wait_one();
                    if (!frame) break;
                    try {
                        if (enable_i420_output_) {
                            if (!decoder->decode_to_videobuffer(
                                    *frame->encoded, frame->video_buffer,
                                    ImageFormat::UNKNOWN, ImageFormat::I420)) {
                                if (!decoder->decode_ex(*frame->encoded, frame->bgr,
                                                        ImageFormat::UNKNOWN, ImageFormat::BGR))
                                    throw std::runtime_error("decode failed");
                            }
                        } else {
                            if (!decoder->decode_ex(*frame->encoded, frame->bgr,
                                                    ImageFormat::UNKNOWN, ImageFormat::BGR))
                                throw std::runtime_error("decode failed");
                            if (output_format_ == OutputFormat::RGBA)
                                cv::cvtColor(frame->bgr, frame->bgr, cv::COLOR_BGR2RGBA);
                        }
                        frame->encoded.reset();

                        if (!input_running_) {
                            std::lock_guard<std::mutex> lk(pending_mutex_);
                            pending_.erase(frame->id);
                            continue;
                        }
                        entry_node_->process(frame);
                    } catch (const std::exception &e) {
                        GRPC_LOGF("PIPELINE", "Decode error for frame %d: %s\n",
                                  frame->id, e.what());
                        std::shared_ptr<std::promise<std::shared_ptr<Frame>>> p;
                        {
                            std::lock_guard<std::mutex> lk(pending_mutex_);
                            auto it = pending_.find(frame->id);
                            if (it != pending_.end()) { p = it->second; pending_.erase(it); }
                        }
                        if (p) p->set_exception(std::current_exception());
                    }
                }
                GRPC_LOGF("DECODE_WORKER", "Pipeline decode thread %d stopped\n", i);
            });
        }

        output_worker_ = std::thread([this]() {
            {
                std::unique_lock<std::mutex> lk(state_mutex_);
                state_cv_.wait(lk, [this] {
                    auto s = server_state_.load(std::memory_order_acquire);
                    return s == ServerState::READY || s == ServerState::SHUTTING_DOWN;
                });
                if (server_state_.load() == ServerState::SHUTTING_DOWN) return;
            }
            GRPC_LOG("PIPELINE", "Output worker started\n");

            while (output_running_) {
                auto frame = result_queue_->wait_one();
                if (!frame) break;

                frame->end_time = std::chrono::high_resolution_clock::now();
                if (frame->dropped) {
                    frame_stats_->dropped_frames.fetch_add(1, std::memory_order_relaxed);
                } else {
                    frame_stats_->total_frames.fetch_add(1, std::memory_order_relaxed);
                    auto lat = std::chrono::duration_cast<std::chrono::microseconds>(
                        frame->end_time - frame->start_time).count();
                    frame_stats_->total_latency_us.fetch_add(
                        static_cast<uint64_t>(lat), std::memory_order_relaxed);
                    frame_stats_->last_success_time_us.store(steady_now_us(),
                        std::memory_order_relaxed);
                    frame_stats_->requests_since_last_success.store(0,
                        std::memory_order_relaxed);
                }

                std::shared_ptr<std::promise<std::shared_ptr<Frame>>> p;
                {
                    std::lock_guard<std::mutex> lk(pending_mutex_);
                    auto it = pending_.find(frame->id);
                    if (it != pending_.end()) { p = it->second; pending_.erase(it); }
                }
                if (p) p->set_value(frame);
            }
            GRPC_LOG("PIPELINE", "Output worker stopped\n");
        });
    }

    /** Stop accepting decode work: stop the decode queue and join the decode workers. */
    void StopInputs() {
        GRPC_LOG("PIPELINE", "StopInputs: stopping imdecode workers\n");
        input_running_ = false;
        imdecode_queue_.stop();
        for (auto &w : imdecode_workers_) if (w.joinable()) w.join();
        GRPC_LOG("PIPELINE", "StopInputs complete\n");
    }

    /**
     * Wait until no requests are pending.
     *
     * Polls every 50 ms and gives up with a warning after timeout_sec_ + 2 seconds.
     */
    void WaitForPipelineDrain() {
        GRPC_LOG("PIPELINE", "WaitForPipelineDrain: waiting for pending promises to drain\n");
        const int timeout_ms = (timeout_sec_ + 2) * 1000;
        const int check_ms = 50;
        int elapsed = 0;
        while (elapsed < timeout_ms) {
            {
                std::lock_guard<std::mutex> lk(pending_mutex_);
                if (pending_.empty()) {
                    GRPC_LOG("PIPELINE", "All pending frames drained\n");
                    return;
                }
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(check_ms));
            elapsed += check_ms;
        }
        GRPC_LOGF("PIPELINE", "WARNING: pipeline drain timeout after %d ms\n", timeout_ms);
    }

    /**
     * Stop the output worker and then every pipeline node, in reverse build order.
     *
     * Also stops the watchdog.
     */
    void StopOutputs() {
        GRPC_LOG("PIPELINE", "StopOutputs: stopping output worker and pipeline nodes\n");
        output_running_ = false;
        result_queue_->stop();
        if (output_worker_.joinable()) output_worker_.join();
        for (auto it = all_nodes_.rbegin(); it != all_nodes_.rend(); ++it)
            (*it)->stop();
        stop_watchdog();
        GRPC_LOG("PIPELINE", "StopOutputs complete\n");
    }

    /**
     * Print and log the server statistics and a one-line STATS_JSON summary.
     *
     * Covers frame and drop counts, average latency, time since the last success, health, decode
     * queue fill, pending requests, and per-node queue occupancy.
     */
    void LogServerStatistics() {
        uint64_t total   = frame_stats_->total_frames.load(std::memory_order_relaxed);
        uint64_t lat_us  = frame_stats_->total_latency_us.load(std::memory_order_relaxed);
        uint64_t dropped = frame_stats_->dropped_frames.load(std::memory_order_relaxed);
        int64_t last_success_us = frame_stats_->last_success_time_us.load(std::memory_order_relaxed);
        uint64_t attempts_since = frame_stats_->requests_since_last_success.load(std::memory_order_relaxed);

        double avg_latency_ms = total > 0 ? (lat_us / (double)total / 1000.0) : 0.0;
        bool healthy = (attempts_since == 0);
        bool have_success = (last_success_us != 0);
        double seconds_since_success = have_success
            ? (steady_now_us() - last_success_us) / 1e6 : 0.0;

        print_and_log("==============================================\n", "STATS");
        print_and_log("       PIPELINE SERVER STATISTICS             \n", "STATS");
        print_and_log("==============================================\n", "STATS");
        printf_and_log("STATS", "Real Frames Processed: %lu\n", total);
        if (total > 0)
            printf_and_log("STATS", "  Average Latency: %.2f ms\n", avg_latency_ms);
        printf_and_log("STATS", "Dropped Frames: %lu\n", dropped);
        printf_and_log("STATS", "Requests Since Last Success: %lu\n",
                       static_cast<unsigned long>(attempts_since));
        if (have_success)
            printf_and_log("STATS", "Seconds Since Last Success: %.2f\n", seconds_since_success);
        else
            print_and_log("Seconds Since Last Success: n/a (no success yet)\n", "STATS");
        printf_and_log("STATS", "Healthy (last attempt succeeded, or none yet): %s\n",
                       healthy ? "true" : "false");
        print_and_log("==============================================\n", "STATS");

        size_t imdecode_used, imdecode_depth;
        {
            std::lock_guard<std::mutex> lk(imdecode_queue_.mutex);
            imdecode_used = imdecode_queue_.queue.size();
            imdecode_depth = imdecode_queue_.queue_depth;
        }
        size_t pending_count;
        {
            std::lock_guard<std::mutex> lk(pending_mutex_);
            pending_count = pending_.size();
        }
        std::ostringstream node_json;
        node_json << "[";
        bool first_node = true;
        for (const auto &node : all_nodes_) {
            auto occ = node->queue_occupancy();
            if (!occ) continue;
            if (!first_node) node_json << ",";
            first_node = false;
            node_json << "{\"id\":\"" << occ->node_id << "\","
                      << "\"input_used\":" << occ->input_used << ","
                      << "\"input_depth\":" << occ->input_depth << ","
                      << "\"result_used\":" << occ->result_used << ","
                      << "\"result_depth\":" << occ->result_depth << "}";
        }
        node_json << "]";

        std::ostringstream json;
        json << "{\"total_frames\":" << total
             << ",\"dropped_frames\":" << dropped
             << ",\"avg_latency_ms\":" << std::fixed << std::setprecision(2) << avg_latency_ms
             << ",\"seconds_since_last_success\":";
        if (have_success) json << std::fixed << std::setprecision(2) << seconds_since_success;
        else json << "null";
        json << ",\"requests_since_last_success\":" << attempts_since
             << ",\"healthy\":" << (healthy ? "true" : "false")
             << ",\"imdecode_queue_used\":" << imdecode_used
             << ",\"imdecode_queue_depth\":" << imdecode_depth
             << ",\"pending_requests\":" << pending_count
             << ",\"node_queues\":" << node_json.str()
             << "}";
        printf_and_log("STATS", "STATS_JSON %s\n", json.str().c_str());
    }

private:
    std::shared_ptr<Ax::AxPipelineNode> entry_node_;
    std::shared_ptr<Ax::BlockingQueue<std::shared_ptr<Frame>>> result_queue_;
    std::vector<std::shared_ptr<Ax::AxPipelineNode>> all_nodes_;
    const std::vector<std::string> &labels_;
    std::unordered_map<std::string, std::string> meta_key_roles_;
    int timeout_sec_;
    int imdecode_threads_count_;
    std::chrono::milliseconds imdecode_queue_timeout_;
    std::shared_ptr<FramePool> frame_pool_;
    OutputFormat output_format_;
    bool enable_i420_output_;

    std::atomic<ServerState> server_state_{ServerState::INITIALIZING};
    std::mutex state_mutex_;
    std::condition_variable state_cv_;
    std::atomic<bool> input_running_{true};
    std::atomic<bool> output_running_{true};

    Ax::BlockingQueue<std::shared_ptr<Frame>> imdecode_queue_;
    std::vector<std::thread> imdecode_workers_;
    std::thread output_worker_;

    std::mutex pending_mutex_;
    std::unordered_map<int, std::shared_ptr<std::promise<std::shared_ptr<Frame>>>> pending_;

    /**
     * Counters updated by the output worker and Infer().
     *
     * Attributes:
     *   total_frames (std::atomic<uint64_t>): Frames completed without being dropped.
     *   total_latency_us (std::atomic<uint64_t>): Sum of their latencies in microseconds.
     *   dropped_frames (std::atomic<uint64_t>): Frames dropped by the pipeline or the decode queue.
     *   last_success_time_us (std::atomic<int64_t>): steady_now_us() of the last completion; 0 if none.
     *   requests_since_last_success (std::atomic<uint64_t>): Requests received since the last
     *     completion.
     */
    struct FrameStats {
        std::atomic<uint64_t> total_frames{0};
        std::atomic<uint64_t> total_latency_us{0};
        std::atomic<uint64_t> dropped_frames{0};
        std::atomic<int64_t>  last_success_time_us{0};
        std::atomic<uint64_t> requests_since_last_success{0};
    };
    std::unique_ptr<FrameStats> frame_stats_;

    /**
     * Watchdog thread body.
     *
     * Once at least one request has succeeded, if at least 3 requests have arrived since the last
     * success and more than watchdog_timeout_ms_ has passed, resolves every pending request as
     * DROPPED, calls on_watchdog_trigger_ and exits. Polls every watchdog_timeout_ms_ clamped to
     * 200-1000 ms.
     */
    void watchdog_loop() {
        static constexpr uint64_t kMinAttemptsBeforeTrigger = 3;
        std::unique_lock<std::mutex> lk(watchdog_mutex_);
        int poll_ms = std::max(200, std::min(watchdog_timeout_ms_, 1000));
        while (!watchdog_stop_.load(std::memory_order_relaxed)) {
            watchdog_cv_.wait_for(lk, std::chrono::milliseconds(poll_ms),
                [this] { return watchdog_stop_.load(std::memory_order_relaxed); });
            if (watchdog_stop_.load(std::memory_order_relaxed)) break;

            int64_t last_success_us = frame_stats_->last_success_time_us.load(std::memory_order_relaxed);
            uint64_t attempts = frame_stats_->requests_since_last_success.load(std::memory_order_relaxed);
            if (last_success_us == 0 || attempts < kMinAttemptsBeforeTrigger) continue;

            int64_t stuck_ms = (steady_now_us() - last_success_us) / 1000;
            if (stuck_ms > watchdog_timeout_ms_) {
                GRPC_LOGF("WATCHDOG",
                    "No successful completion for %ldms despite %lu request(s) "
                    "attempted since — resolving in-flight requests as DROPPED "
                    "and triggering a restart\n",
                    static_cast<long>(stuck_ms), attempts);

                std::vector<std::shared_ptr<std::promise<std::shared_ptr<Frame>>>> to_resolve;
                {
                    std::lock_guard<std::mutex> plk(pending_mutex_);
                    to_resolve.reserve(pending_.size());
                    for (auto &[fid, prom] : pending_) {
                        auto dropped = std::make_shared<Frame>();
                        dropped->id = fid;
                        dropped->dropped = true;
                        dropped->drop_reason = "server restarted by watchdog";
                        prom->set_value(dropped);
                    }
                    pending_.clear();
                }

                if (on_watchdog_trigger_) on_watchdog_trigger_();
                break;
            }
        }
    }

    /** Stop and join the watchdog thread if it is running. */
    void stop_watchdog() {
        if (!watchdog_thread_.joinable()) return;
        watchdog_stop_.store(true, std::memory_order_relaxed);
        watchdog_cv_.notify_all();
        watchdog_thread_.join();
    }

    int watchdog_timeout_ms_ = 0;
    std::function<void()> on_watchdog_trigger_;
    std::thread watchdog_thread_;
    std::atomic<bool> watchdog_stop_{false};
    std::mutex watchdog_mutex_;
    std::condition_variable watchdog_cv_;

    /** Statistics thread body: log statistics every stats_interval_ms_ until stopped. */
    void stats_loop() {
        std::unique_lock<std::mutex> lk(stats_mutex_);
        while (!stats_stop_.load(std::memory_order_relaxed)) {
            stats_cv_.wait_for(lk, std::chrono::milliseconds(stats_interval_ms_),
                [this] { return stats_stop_.load(std::memory_order_relaxed); });
            if (stats_stop_.load(std::memory_order_relaxed)) break;
            LogServerStatistics();
        }
    }

    /** Stop and join the statistics thread if it is running. */
    void stop_stats_thread() {
        if (!stats_thread_.joinable()) return;
        stats_stop_.store(true, std::memory_order_relaxed);
        stats_cv_.notify_all();
        stats_thread_.join();
    }

    int stats_interval_ms_ = 1500;
    std::thread stats_thread_;
    std::atomic<bool> stats_stop_{false};
    std::mutex stats_mutex_;
    std::condition_variable stats_cv_;
};

}


// Process-wide control flags, set from signal handlers and from the watchdog.
// SIGRTMIN+1 requests a pipeline restart and SIGRTMIN+2 requests a statistics dump.
static std::atomic<bool>    g_shutdown_requested{false};
static std::mutex           g_restart_mutex;
static std::condition_variable g_restart_cv;
#define SIGNAL_RESTART      (SIGRTMIN + 1)
#define SIGNAL_PRINT_STATS  (SIGRTMIN + 2)
static std::atomic<bool>    g_restart_signal_received{false};
static std::atomic<bool>    g_stats_signal_received{false};
static std::atomic<uint64_t> g_watchdog_restart_count{0};

/**
 * Handle SIGINT and SIGTERM by requesting shutdown.
 *
 * Args:
 *   signal (int): The received signal number.
 */
void signal_handler(int signal) {
    if (signal == SIGINT || signal == SIGTERM) {
        std::cout << "\n[SYSTEM] Shutdown signal received. Stopping server...\n";
        GRPC_LOG("SYSTEM", "Shutdown signal received\n");
        g_shutdown_requested = true;
        g_restart_cv.notify_all();
    }
}

/**
 * Handle the real-time signals for restart and statistics.
 *
 * Args:
 *   sig (int): SIGNAL_RESTART or SIGNAL_PRINT_STATS.
 */
void realtime_signal_handler(int sig, siginfo_t * , void * ) {
    if (sig == SIGNAL_RESTART) {
        g_restart_signal_received.store(true, std::memory_order_release);
        g_restart_cv.notify_all();
    } else if (sig == SIGNAL_PRINT_STATS) {
        g_stats_signal_received.store(true, std::memory_order_release);
        g_restart_cv.notify_all();
    }
}

/** Register realtime_signal_handler for SIGNAL_RESTART and SIGNAL_PRINT_STATS and log the outcome. */
void setup_custom_signals() {
    struct sigaction sa;
    sa.sa_sigaction = realtime_signal_handler;
    sa.sa_flags = SA_SIGINFO | SA_RESTART;
    sigemptyset(&sa.sa_mask);
    sigaddset(&sa.sa_mask, SIGNAL_RESTART);
    sigaddset(&sa.sa_mask, SIGNAL_PRINT_STATS);
    if (sigaction(SIGNAL_RESTART, &sa, nullptr) == -1)
        GRPC_LOGF("SIGNAL", "Warning: Failed to register SIGNAL_RESTART (%d): %s\n",
                  SIGNAL_RESTART, strerror(errno));
    else
        GRPC_LOGF("STARTUP", "Registered SIGNAL_RESTART (signal %d)\n", SIGNAL_RESTART);
    if (sigaction(SIGNAL_PRINT_STATS, &sa, nullptr) == -1)
        GRPC_LOGF("SIGNAL", "Warning: Failed to register SIGNAL_PRINT_STATS (%d): %s\n",
                  SIGNAL_PRINT_STATS, strerror(errno));
    else
        GRPC_LOGF("STARTUP", "Registered SIGNAL_PRINT_STATS (signal %d)\n",
                  SIGNAL_PRINT_STATS);
}

/** Set the gperftools allocator release rate to 10.0. */
void ConfigureMemoryAllocator() {
    MallocExtension::instance()->SetMemoryReleaseRate(10.0);
}

/**
 * Configure a gRPC ServerBuilder for the service.
 *
 * Listens on 0.0.0.0:<port> without TLS, registers the service, and sets a resource quota and
 * the concurrent stream limit. high_bandwidth additionally tunes buffer sizes, HTTP/2 windows,
 * keepalive and connection limits for throughput.
 *
 * Args:
 *   builder (ServerBuilder&): Builder to configure.
 *   service (grpc::Service*): Service to register.
 *   port (int): TCP port.
 *   quota_mb (int): Resource quota in megabytes.
 *   max_streams (int): Maximum concurrent streams.
 *   high_bandwidth (bool): Select the throughput-oriented settings.
 *   restart_count (int): Used to give each quota a distinct name.
 */
void ConfigureServerBuilder(ServerBuilder &builder, grpc::Service *service,
                            int port, int quota_mb, int max_streams,
                            bool high_bandwidth, int restart_count)
{
    std::string addr = "0.0.0.0:" + std::to_string(port);
    builder.AddListeningPort(addr, grpc::InsecureServerCredentials());
    builder.RegisterService(service);
    std::string name = "axinferencenet_quota_" + std::to_string(restart_count);

    if (high_bandwidth) {
        grpc::ResourceQuota quota(name);
        quota.Resize(quota_mb * 1024 * 1024);
        builder.SetResourceQuota(quota);
        builder.AddChannelArgument(GRPC_ARG_MAX_CONCURRENT_STREAMS, max_streams);
        GRPC_LOG("STARTUP", "Configuring gRPC for RAW THROUGHPUT\n");
        builder.AddChannelArgument("grpc.http2.bdp_probe", 0);
        builder.AddChannelArgument("grpc.tcp_receive_buffer_size", 16 * 1024 * 1024);
        builder.AddChannelArgument("grpc.tcp_send_buffer_size", 16 * 1024 * 1024);
        builder.AddChannelArgument("grpc.experimental.tcp_read_chunk_size", 4 * 1024 * 1024);
        builder.AddChannelArgument("grpc.http2.initial_connection_window_size", 16 * 1024 * 1024);
        builder.AddChannelArgument("grpc.http2.initial_stream_window_size", 4 * 1024 * 1024);
        builder.AddChannelArgument("grpc.http2.lookahead_bytes", 4 * 1024 * 1024);
        builder.AddChannelArgument("grpc.http2.max_frame_size", 1 * 1024 * 1024);
        builder.AddChannelArgument("grpc.max_receive_message_length", -1);
        builder.AddChannelArgument(GRPC_ARG_KEEPALIVE_TIME_MS, 60000);
        builder.AddChannelArgument(GRPC_ARG_KEEPALIVE_TIMEOUT_MS, 20000);
        builder.AddChannelArgument(GRPC_ARG_KEEPALIVE_PERMIT_WITHOUT_CALLS, 1);
        builder.AddChannelArgument(
            GRPC_ARG_HTTP2_MIN_RECV_PING_INTERVAL_WITHOUT_DATA_MS, 10000);
        builder.AddChannelArgument(GRPC_ARG_ENABLE_RETRIES, 0);
        builder.AddChannelArgument(GRPC_ARG_MAX_CONNECTION_IDLE_MS, 15000);
        builder.AddChannelArgument(GRPC_ARG_MAX_CONNECTION_AGE_MS, 3600000);
        builder.AddChannelArgument(GRPC_ARG_MAX_CHANNEL_TRACE_EVENT_MEMORY_PER_NODE, 0);
    } else {
        GRPC_LOG("STARTUP", "Configuring gRPC with Default mode)\n");
        builder.AddChannelArgument("grpc.http2.bdp_probe", 1);
        builder.AddChannelArgument("grpc.optimization_target", "throughput");
        grpc::ResourceQuota quota(name);
        quota.Resize(quota_mb * 1024 * 1024);
        quota.SetMaxThreads(2500);
        builder.SetResourceQuota(quota);
        builder.AddChannelArgument(GRPC_ARG_MAX_CONCURRENT_STREAMS, max_streams);
    }
}


/**
 * Private implementation of Ax::GrpcServer.
 *
 * Owns the configuration and the serve loop that builds the pipeline and gRPC server and
 * tears them down on restart or shutdown.
 */
class Ax::GrpcServer::Impl {
public:
    /** Store the configuration and map output_format to an OutputFormat; unknown values mean BGR. */
    Impl(const GrpcServerConfig &cfg, Ax::Logger &logger)
        : cfg_(cfg), logger_(logger)
    {
        if (cfg_.output_format == "I420" || cfg_.output_format == "i420")
            output_format_ = OutputFormat::I420;
        else if (cfg_.output_format == "RGBA" || cfg_.output_format == "rgba")
            output_format_ = OutputFormat::RGBA;
        else
            output_format_ = OutputFormat::BGR;
    }

    /** Request shutdown of the serve loop. */
    void request_shutdown() {
        g_shutdown_requested.store(true, std::memory_order_release);
        g_restart_cv.notify_all();
    }

    /**
     * Run the serve loop until shutdown is requested.
     *
     * Each iteration builds the pipeline, creates the service and gRPC server, marks the service
     * READY and waits. It leaves the wait on shutdown, a restart request (signal or watchdog),
     * or after restart_interval_s elapses, and handles statistics signals without restarting.
     * It then stops the server and the pipeline and, on a restart, loops. Returns immediately
     * if the pipeline cannot be built or the gRPC server fails to start.
     */
    void serve() {
        print_and_log("==============================================\n");
        print_and_log("    AxInferenceNet GRPC Server (pipeline)    \n");
        print_and_log("==============================================\n");
        printf_and_log("PIPELINE", "Pipeline spec: %s\n", cfg_.pipeline_spec_path.c_str());
        printf_and_log("STARTUP",  "Output format: %s\n", cfg_.output_format.c_str());

        std::signal(SIGINT,  signal_handler);
        std::signal(SIGTERM, signal_handler);
        setup_custom_signals();

        int restart_count = 0;
        while (!g_shutdown_requested) {
            if (restart_count > 0) {
                printf_and_log("PIPELINE", "Pipeline restart #%d\n", restart_count);
            }

            Ax::PipelineBuilder builder(cfg_.pipeline_spec_path, logger_);
            Ax::BuiltPipeline pipeline;
            try {
                pipeline = builder.build();
            } catch (const std::exception &e) {
                std::cerr << "FATAL: PipelineBuilder::build() failed: " << e.what() << std::endl;
                return;
            }
            printf_and_log("PIPELINE", "Pipeline built successfully\n");

            size_t pool_size = static_cast<size_t>(cfg_.max_streams * 1.5);
            auto frame_pool  = std::make_shared<FramePool>(pool_size);

            auto service = std::make_unique<PipelineService>(
                pipeline.entry_node,
                pipeline.result_queue,
                pipeline.all_nodes,
                cfg_.labels,
                cfg_.timeout_s,
                cfg_.imdecode_threads,
                frame_pool,
                output_format_,
                cfg_.watchdog_timeout_ms,
                [] {
                    g_watchdog_restart_count.fetch_add(1, std::memory_order_relaxed);
                    g_restart_signal_received.store(true, std::memory_order_release);
                    g_restart_cv.notify_all();
                },
                cfg_.imdecode_queue_timeout_ms,
                cfg_.imdecode_queue_depth,
                cfg_.meta_key_roles);

            service->StartWorkers();

            ServerBuilder sb;
            ConfigureServerBuilder(sb, service.get(),
                                   cfg_.port, cfg_.quota_mb, cfg_.max_streams,
                                   cfg_.high_bandwidth, restart_count);

            print_and_log("Building and starting gRPC server (pipeline mode)...\n", "STARTUP");
            std::unique_ptr<Server> server(sb.BuildAndStart());
            if (!server) {
                std::cerr << "Failed to start gRPC server" << std::endl;
                return;
            }

            printf_and_log("STARTUP",
                           "Server listening on 0.0.0.0:%d (pipeline mode)\n", cfg_.port);
            service->SetReady();

            // Wait for shutdown, a restart request or a statistics request; a timeout (when restart_interval_s > 0) falls through to a restart.
            for (;;) {
                std::unique_lock<std::mutex> lock(g_restart_mutex);
                auto wake_cond = [&] {
                    return g_shutdown_requested.load(std::memory_order_acquire) ||
                           g_restart_signal_received.load(std::memory_order_acquire) ||
                           g_stats_signal_received.load(std::memory_order_acquire);
                };
                if (cfg_.restart_interval_s > 0)
                    g_restart_cv.wait_for(lock,
                        std::chrono::seconds(cfg_.restart_interval_s), wake_cond);
                else
                    g_restart_cv.wait(lock, wake_cond);

                bool shutdown = g_shutdown_requested.load(std::memory_order_acquire);
                bool restart_signal = g_restart_signal_received.exchange(
                    false, std::memory_order_acq_rel);
                bool stats_signal = g_stats_signal_received.exchange(
                    false, std::memory_order_acq_rel);
                lock.unlock();

                if (shutdown || restart_signal) break;

                if (stats_signal) {
                    printf_and_log("SYSTEM", "Statistics signal received (PID: %d)\n", getpid());
                    service->LogServerStatistics();
                    printf_and_log("STATS",
                        "Watchdog-Triggered Restarts (this process): %lu\n",
                        static_cast<unsigned long>(
                            g_watchdog_restart_count.load(std::memory_order_relaxed)));
                    continue;
                }

                break;
            }

            print_and_log("Shutting down gRPC server (pipeline)...\n", "SYSTEM");
            server->Shutdown();
            server.reset();

            service->StopInputs();
            service->WaitForPipelineDrain();
            service->StopOutputs();
            service->LogServerStatistics();
            printf_and_log("STATS", "Watchdog-Triggered Restarts (this process): %lu\n",
                           static_cast<unsigned long>(
                               g_watchdog_restart_count.load(std::memory_order_relaxed)));

            service.reset();
            frame_pool.reset();
            print_and_log("Pipeline resources released.\n", "SYSTEM");

            if (!g_shutdown_requested && cfg_.restart_interval_s > 0) {
                std::this_thread::sleep_for(std::chrono::seconds(1));
                restart_count++;
            }
        }
        print_and_log("Pipeline server shutdown complete.\n", "SYSTEM");
    }

private:
    GrpcServerConfig cfg_;
    Ax::Logger      &logger_;
    OutputFormat     output_format_;
};


Ax::GrpcServer::GrpcServer(const GrpcServerConfig &cfg, Ax::Logger &logger)
    : impl_(std::make_unique<Impl>(cfg, logger))
{
    ConfigureMemoryAllocator();
}

Ax::GrpcServer::~GrpcServer() = default;

void Ax::GrpcServer::serve_forever() {
    impl_->serve();
}

void Ax::GrpcServer::request_shutdown() {
    impl_->request_shutdown();
}
