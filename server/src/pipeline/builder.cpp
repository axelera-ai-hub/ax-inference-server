
// Implementation of PipelineBuilder: builds a graph of pipeline nodes from a JSON spec.
// Also holds the helpers that parse the axnet config string and replicate inference nodes.
#include "pipeline/builder.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <stdexcept>
#include <string>
#include <unordered_map>

#include "axruntime/axruntime.hpp"

#if __has_include(<nlohmann/json.hpp>)
#   include <nlohmann/json.hpp>
    using json = nlohmann::json;
#   define HAVE_NLOHMANN_JSON 1
#else
#   define HAVE_NLOHMANN_JSON 0
#endif

#include "AxInferenceNet.hpp"
#include "AxLog.hpp"
#include "pipeline/node.h"
#include "pipeline/frame.h"
#include "pipeline/predicate.h"
#include "nodes/inference.h"
#include "nodes/filter.h"
#include "nodes/iter.h"
#include "nodes/collect.h"
#include "nodes/guard.h"
#include "nodes/condition.h"
#include "nodes/rename.h"
#include "pipeline/timed_queue_push.h"
#include "common/io_uring_logger.hpp"

namespace {

/**
 * One entry of the GRPC_AXNET_CONFIG string.
 *
 * Attributes:
 *   net_id (std::string): Net identifier as written in the config string.
 *   device_indices (std::vector<int>): Indices into the device list the net runs on.
 *   num_cores (int): Number of cores (children) per device group. Default 4.
 */
struct ParsedNetSpec {
    std::string net_id;
    std::vector<int> device_indices;
    int num_cores{4};
};

/**
 * Parse a GRPC_AXNET_CONFIG style string into per-replica device assignments.
 *
 * The string is a ';'-separated list of pairs: a net id followed by "[devices:]<i>,<j>,...-<n>"
 * with device indices and a trailing core count, for example "net;devices:0,1-4". Each valid
 * pair yields one entry; malformed pairs are skipped.
 *
 * Args:
 *   cfg (const std::string&): Config string; may be empty.
 *
 * Returns:
 *   std::vector<ParsedNetSpec>: One entry per valid pair, in order.
 */
std::vector<ParsedNetSpec> parse_axnet_config(const std::string &cfg)
{
    std::vector<ParsedNetSpec> result;
    std::vector<std::string> tokens;
    size_t s = 0, e = cfg.find(';');
    while (e != std::string::npos) {
        tokens.push_back(cfg.substr(s, e - s));
        s = e + 1;
        e = cfg.find(';', s);
    }
    tokens.push_back(cfg.substr(s));

    for (size_t i = 0; i + 1 < tokens.size(); i += 2) {
        ParsedNetSpec spec;
        spec.net_id = tokens[i];
        std::string dev_part = tokens[i + 1];
        if (dev_part.starts_with("devices:"))
            dev_part = dev_part.substr(8);
        auto last_dash = dev_part.rfind('-');
        if (last_dash == std::string::npos) continue;
        try {
            spec.num_cores = std::stoi(dev_part.substr(last_dash + 1));
            std::string ids = dev_part.substr(0, last_dash);
            size_t p = 0, q = ids.find(',');
            while (q != std::string::npos) {
                spec.device_indices.push_back(std::stoi(ids.substr(p, q - p)));
                p = q + 1; q = ids.find(',', p);
            }
            spec.device_indices.push_back(std::stoi(ids.substr(p)));
            if (!spec.device_indices.empty()) result.push_back(spec);
        } catch (...) { continue; }
    }
    return result;
}

/**
 * Join the names of the devices selected by a spec into a comma-separated string.
 *
 * Args:
 *   spec (const ParsedNetSpec&): Spec whose device indices are looked up.
 *   devices (const axrDeviceInfo*): Device list from the runtime; indices are not range-checked.
 *
 * Returns:
 *   std::string: Device names separated by commas.
 */
std::string build_devices_string(const ParsedNetSpec &spec,
                                 const axrDeviceInfo *devices)
{
    std::string s;
    for (size_t i = 0; i < spec.device_indices.size(); ++i) {
        if (i) s += ",";
        s += devices[spec.device_indices[i]].name;
    }
    return s;
}

/**
 * Pipeline node that spreads frames over several InferenceNode replicas in round-robin order.
 *
 * Used when a net is configured on more than one device group. The next callback and stop()
 * are forwarded to every replica. It does not report queue occupancy.
 */
class RoundRobinInferenceGroup : public Ax::AxPipelineNode {
public:
    explicit RoundRobinInferenceGroup(std::vector<std::shared_ptr<Ax::InferenceNode>> children)
        : children_(std::move(children))
    {}

    void process(std::shared_ptr<Ax::Frame> frame) override {
        const size_t idx = counter_.fetch_add(1, std::memory_order_relaxed) % children_.size();
        children_[idx]->process(std::move(frame));
    }

    void set_next(Ax::PipelineCallback cb) override {
        for (auto &child : children_) child->set_next(cb);
    }

    void stop() override {
        for (auto &child : children_) child->stop();
    }

private:
    std::vector<std::shared_ptr<Ax::InferenceNode>> children_;
    std::atomic<size_t> counter_{0};
};

}

namespace Ax {

// Store the spec path and logger; the spec is read in build().
PipelineBuilder::PipelineBuilder(std::string spec_path, Ax::Logger &logger)
    : spec_path_(std::move(spec_path)), logger_(logger)
{}

/**
 * Read the JSON spec and construct the connected pipeline nodes.
 *
 * Spec layout (top-level keys):
 *   nets (object, optional): name -> {axnet_path, axnet_config}.
 *   global (object, required): optional result_queue_depth and pipeline_depth.
 *   predicates (object, optional): name -> {type, ...}; type is "meta_key_exists",
 *     "kpts_conf_gt" or "plugin".
 *   nodes (array): each has id and type ("net", "sink", "filter", "roi_iter", "roi_collect",
 *     "condition", "rename" or "loop_guard") plus type-specific fields and wiring keys
 *     (next, skip_to, continue_to, exit_to, then, else).
 *   entry (string): id of the node that receives decoded frames.
 *
 * While reading nets, GRPC_AXNET_CONFIG is set temporarily and then restored to its prior
 * value; this modifies the process environment.
 *
 * Returns:
 *   BuiltPipeline: Entry node, shared result queue, all nodes in spec order, and the
 *     pipeline depth (scaled by the largest replica count when greater than 1).
 *
 * Raises:
 *   std::runtime_error: If nlohmann/json is unavailable, the spec cannot be opened or parsed,
 *     no Axelera device is found, a node references an unknown net, predicate or node, or a
 *     node or predicate type is unsupported.
 */
BuiltPipeline PipelineBuilder::build()
{
#if !HAVE_NLOHMANN_JSON
    throw std::runtime_error(
        "PipelineBuilder::build() requires nlohmann/json. "
        "Add nlohmann-json3-dev to the build or install it.");
#else
    std::ifstream f(spec_path_);
    if (!f) {
        throw std::runtime_error("PipelineBuilder: cannot open spec: " + spec_path_);
    }
    json spec;
    try { spec = json::parse(f); }
    catch (const json::exception &ex) {
        throw std::runtime_error(
            "PipelineBuilder: JSON parse error in " + spec_path_ + ": " + ex.what());
    }

    json nets_json;
    if (spec.contains("nets") && !spec.at("nets").empty()) {
        nets_json = spec.at("nets");
    } else {
        nets_json = json::object();
    }
    const json &global_json = spec.at("global");

    const char *orig_env_ptr = std::getenv("GRPC_AXNET_CONFIG");
    std::string saved_env = orig_env_ptr ? orig_env_ptr : "";

    struct NetInfo {
        std::string axnet_path;
        std::string axnet_config;
        std::vector<InferenceNetProperties> props_list;
    };
    std::unordered_map<std::string, NetInfo> net_map;

    if (!nets_json.empty()) {
        auto ctx = axr::to_ptr(axr_create_context());
        axrDeviceInfo *devices_ptr = nullptr;
        auto num_devices = axr_list_devices(ctx.get(), &devices_ptr);
        if (num_devices <= 0 || !devices_ptr) {
            throw std::runtime_error("PipelineBuilder: no Axelera devices found");
        }

        for (const auto &[name, net_json] : nets_json.items()) {
            NetInfo ni;
            ni.axnet_path = net_json.at("axnet_path").get<std::string>();
            ni.axnet_config = net_json.at("axnet_config").get<std::string>();

            ::setenv("GRPC_AXNET_CONFIG", ni.axnet_config.c_str(), 1);
            auto base_props = Ax::read_inferencenet_properties(ni.axnet_path, logger_);

            auto specs = parse_axnet_config(ni.axnet_config);
            if (specs.empty()) {
                ni.props_list.push_back(base_props);
            } else {
                for (const auto &spec : specs) {
                    auto props = base_props;
                    props.devices      = build_devices_string(spec, devices_ptr);
                    props.num_children = spec.num_cores;
                    ni.props_list.push_back(std::move(props));
                }
            }

            net_map[name] = std::move(ni);
        }

        if (!saved_env.empty()) ::setenv("GRPC_AXNET_CONFIG", saved_env.c_str(), 1);
        else                     ::unsetenv("GRPC_AXNET_CONFIG");
    }

    // Default result queue depth: twice the node count, but at least 16.
    const size_t default_result_queue_depth =
        std::max<size_t>(spec.at("nodes").size() * 2, 16);
    const size_t result_queue_depth = global_json.contains("result_queue_depth")
        ? static_cast<size_t>(global_json.at("result_queue_depth").get<int>())
        : default_result_queue_depth;
    auto result_queue =
        std::make_shared<BlockingQueue<std::shared_ptr<Frame>>>(result_queue_depth);
    IoUringLogger::instance().logf("PIPELINE", "result_queue_ depth: %zu (%s)\n",
                 result_queue_depth,
                 global_json.contains("result_queue_depth") ? "explicit override" : "auto-derived");

    std::unordered_map<std::string, std::shared_ptr<Predicate>> predicate_map;
    if (spec.contains("predicates")) {
        for (const auto &[pname, pjson] : spec.at("predicates").items()) {
            const std::string ptype = pjson.at("type").get<std::string>();
            if (ptype == "meta_key_exists") {
                predicate_map[pname] = std::make_shared<MetaKeyExistsPredicate>(
                    pjson.at("meta_key").get<std::string>());
            } else if (ptype == "kpts_conf_gt") {
                predicate_map[pname] = std::make_shared<KptsConfidencePredicate>(
                    pjson.at("meta_key").get<std::string>(),
                    pjson.at("indices").get<std::vector<int>>(),
                    pjson.at("value").get<float>());
            } else if (ptype == "plugin") {
                predicate_map[pname] = std::make_shared<PluginPredicate>(
                    pjson.at("so_path").get<std::string>());
            } else {
                throw std::runtime_error(
                    "PipelineBuilder: predicate '" + pname + "' has type '" + ptype +
                    "' which is not yet ported (only \"meta_key_exists\", "
                    "\"kpts_conf_gt\", and \"plugin\" are supported)");
            }
        }
    }

    const json &nodes_json = spec.at("nodes");
    const std::string entry_id = spec.at("entry").get<std::string>();

    std::unordered_map<std::string, std::shared_ptr<AxPipelineNode>> node_map;
    std::vector<std::string> node_order;

    // Largest number of replicas of any net node; scales pipeline_depth at the end.
    size_t max_net_replicas = 1;

    for (const auto &nj : nodes_json) {
        const std::string id   = nj.at("id").get<std::string>();
        const std::string type = nj.at("type").get<std::string>();
        node_order.push_back(id);

        std::shared_ptr<AxPipelineNode> node;

        if (type == "net") {
            const std::string net_name = nj.at("net").get<std::string>();
            auto it = net_map.find(net_name);
            if (it == net_map.end()) {
                throw std::runtime_error(
                    "PipelineBuilder: node '" + id + "' references unknown net '" + net_name + "'");
            }
            ::setenv("GRPC_AXNET_CONFIG", it->second.axnet_config.c_str(), 1);
            const auto &props_list = it->second.props_list;
            max_net_replicas = std::max(max_net_replicas, props_list.size());
            std::vector<std::shared_ptr<InferenceNode>> children;
            children.reserve(props_list.size());
            const bool has_queue_depth_override = nj.contains("queue_depth");
            const size_t queue_depth_override = has_queue_depth_override
                ? static_cast<size_t>(nj.at("queue_depth").get<int>()) : 0;
            // Default node queue timeout is 2000 ms; queue depth defaults to the replica's num_children (min 1).
            const auto node_queue_timeout =
                std::chrono::milliseconds(nj.value("queue_timeout_ms", 2000));
            for (size_t ci = 0; ci < props_list.size(); ++ci) {
                const auto &props = props_list[ci];
                std::cerr << "[PipelineBuilder] node='" << id << "' net='" << net_name
                          << "' replica=" << ci << "/" << props_list.size()
                          << " devices='" << props.devices
                          << "' num_children=" << props.num_children
                          << " GRPC_AXNET_CONFIG=" << it->second.axnet_config << "\n";
                const std::string child_id = props_list.size() > 1
                    ? (id + "_replica" + std::to_string(ci))
                    : id;
                const size_t node_queue_depth = has_queue_depth_override
                    ? queue_depth_override
                    : static_cast<size_t>(std::max(1, props.num_children));
                children.push_back(std::make_shared<InferenceNode>(
                    child_id, props, logger_,
                    // Dropped frames are reported to the shared result queue; the join timeout is 5000 ms.
                    node_queue_timeout, result_queue,
                    std::chrono::milliseconds(5000), node_queue_depth));
            }
            if (!saved_env.empty()) ::setenv("GRPC_AXNET_CONFIG", saved_env.c_str(), 1);
            else                     ::unsetenv("GRPC_AXNET_CONFIG");

            node = (children.size() == 1)
                ? std::static_pointer_cast<AxPipelineNode>(children[0])
                : std::make_shared<RoundRobinInferenceGroup>(std::move(children));

        // Terminal node: pushes frames onto the result queue read by the server's output worker.
        } else if (type == "sink") {
            auto q = result_queue;
            struct SinkNode : AxPipelineNode {
                std::shared_ptr<BlockingQueue<std::shared_ptr<Frame>>> q_;
                explicit SinkNode(std::shared_ptr<BlockingQueue<std::shared_ptr<Frame>>> q)
                    : q_(std::move(q)) {}
                void process(std::shared_ptr<Frame> frame) override {
                    if (!try_push_for(*q_, frame, std::chrono::milliseconds(2000))) {
                        auto frame_id = frame ? frame->id : -1;
                        IoUringLogger::instance().logf("PIPELINE",
                            "SinkNode: result_queue full after 2000ms, dropping frame %d "
                            "(client will see the pipeline timeout)\n", frame_id);
                    }
                }
            };
            node = std::make_shared<SinkNode>(q);

        } else if (type == "filter") {
            FilterNodeConfig cfg;
            cfg.meta_key = nj.at("meta_key").get<std::string>();
            if (nj.contains("classes"))
                cfg.classes = nj.at("classes").get<std::vector<int>>();
            if (nj.contains("min_score")) cfg.min_score = nj.at("min_score").get<float>();
            if (nj.contains("max_score")) cfg.max_score = nj.at("max_score").get<float>();
            if (nj.contains("min_width")) cfg.min_width = nj.at("min_width").get<int>();
            if (nj.contains("min_height")) cfg.min_height = nj.at("min_height").get<int>();
            if (nj.contains("top_k")) cfg.top_k = nj.at("top_k").get<int>();
            cfg.which = nj.value("which", std::string("all"));
            node = std::make_shared<FilterNode>(std::move(cfg));

        } else if (type == "roi_iter") {
            RoiIterNodeConfig cfg;
            cfg.meta_key = nj.at("meta_key").get<std::string>();
            cfg.crop_padding = nj.value("crop_padding", 0.0f);
            node = std::make_shared<RoiIterNode>(std::move(cfg));

        } else if (type == "roi_collect") {
            RoiCollectNodeConfig cfg;
            cfg.det_meta_key = nj.at("det_meta_key").get<std::string>();
            const auto &cmk = nj.at("cls_meta_key");
            if (cmk.is_array()) {
                cfg.cls_meta_keys = cmk.get<std::vector<std::string>>();
            } else {
                cfg.cls_meta_keys = { cmk.get<std::string>() };
            }
            node = std::make_shared<RoiCollectNode>(std::move(cfg));

        } else if (type == "condition") {
            const std::string pred_name = nj.at("predicate").get<std::string>();
            auto pred_it = predicate_map.find(pred_name);
            if (pred_it == predicate_map.end()) {
                throw std::runtime_error(
                    "PipelineBuilder: node '" + id + "' references unknown predicate '" +
                    pred_name + "'");
            }
            node = std::make_shared<ConditionNode>(pred_it->second);

        } else if (type == "rename") {
            node = std::make_shared<RenameNode>(
                nj.at("rename_from").get<std::string>(),
                nj.at("rename_to").get<std::string>());

        } else if (type == "loop_guard") {
            LoopGuardNodeConfig cfg;
            const std::string until_name = nj.at("until").get<std::string>();
            auto pred_it = predicate_map.find(until_name);
            if (pred_it == predicate_map.end()) {
                throw std::runtime_error(
                    "PipelineBuilder: node '" + id + "' references unknown predicate '" +
                    until_name + "'");
            }
            cfg.until = pred_it->second;
            cfg.max_iters = nj.value("max_iters", 3);
            cfg.dispatch_queue_depth =
                static_cast<size_t>(nj.value("dispatch_queue_depth", 8));
            cfg.queue_timeout =
                std::chrono::milliseconds(nj.value("queue_timeout_ms", 2000));
            node = std::make_shared<LoopGuardNode>(std::move(cfg));

        } else {
            throw std::runtime_error(
                "PipelineBuilder: unsupported node type '" + type +
                "' for node '" + id + "'");
        }

        node_map[id] = node;
    }

    // Create a callback that forwards a frame to the named node; throws if the node is unknown.
    auto callback_to = [&node_map](const std::string &from_id,
                           const std::string &to_id) -> PipelineCallback {
        auto to_it = node_map.find(to_id);
        if (to_it == node_map.end()) {
            throw std::runtime_error(
                "PipelineBuilder: node '" + from_id + "' has unknown ref '" + to_id + "'");
        }
        auto target = to_it->second;
        return [target](std::shared_ptr<Frame> fr) { target->process(std::move(fr)); };
    };

    for (const auto &nj : nodes_json) {
        const std::string from_id = nj.at("id").get<std::string>();
        const std::string type = nj.at("type").get<std::string>();
        auto from_node = node_map.at(from_id);

        // Only the first entry of a "next" array is used.
        if (nj.contains("next")) {
            std::string to_id;
            if (nj["next"].is_array()) {
                if (!nj["next"].empty()) to_id = nj["next"][0].get<std::string>();
            } else {
                to_id = nj["next"].get<std::string>();
            }
            if (!to_id.empty())
                from_node->set_next(callback_to(from_id, to_id));
        }

        if (type == "roi_iter") {
            auto *roi_iter = dynamic_cast<RoiIterNode *>(from_node.get());
            roi_iter->set_skip(callback_to(from_id, nj.at("skip_to").get<std::string>()));
        } else if (type == "loop_guard") {
            auto *loop_guard = dynamic_cast<LoopGuardNode *>(from_node.get());
            loop_guard->set_continue(
                callback_to(from_id, nj.at("continue_to").get<std::string>()));
            loop_guard->set_exit(callback_to(from_id, nj.at("exit_to").get<std::string>()));
        } else if (type == "condition") {
            auto *condition = dynamic_cast<ConditionNode *>(from_node.get());
            condition->set_then(callback_to(from_id, nj.at("then").get<std::string>()));
            condition->set_else(callback_to(from_id, nj.at("else").get<std::string>()));
        }
    }

    BuiltPipeline result;
    result.entry_node   = node_map.at(entry_id);
    result.result_queue = result_queue;
    for (const auto &id : node_order) {
        result.all_nodes.push_back(node_map.at(id));
    }
    // pipeline_depth defaults to 0 (unset).
    result.pipeline_depth = global_json.value("pipeline_depth", 0);
    if (result.pipeline_depth > 0 && max_net_replicas > 1) {
        result.pipeline_depth *= static_cast<int>(max_net_replicas);
    }
    return result;
#endif
}

}
