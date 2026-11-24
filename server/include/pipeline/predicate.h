
#pragma once

// Boolean tests on a Frame, used when building condition nodes: built-in predicates and a dlopen plugin wrapper.

#include <dlfcn.h>

#include <stdexcept>
#include <string>
#include <vector>

#include "AxMetaKptsDetection.hpp"
#include "pipeline/frame.h"

namespace Ax {

/** Abstract boolean test on a frame. */
class Predicate {
public:
    virtual ~Predicate() = default;
    /**
     * Evaluate the predicate.
     *
     * Args:
     *     frame (const Frame &): Frame to test.
     *
     * Returns:
     *     bool: The result of the test.
     */
    virtual bool eval(const Frame &frame) const = 0;
};

/** True when the frame's meta map contains a given key. */
class MetaKeyExistsPredicate : public Predicate {
public:
    /** Args: meta_key (std::string): Key to look for in Frame::meta. */
    explicit MetaKeyExistsPredicate(std::string meta_key) : meta_key_(std::move(meta_key)) {}

    bool eval(const Frame &frame) const override
    {
        return frame.meta.count(meta_key_) > 0;
    }

private:
    std::string meta_key_;
};

/**
 * True when selected keypoints of the first detection are all above a visibility threshold.
 *
 * Evaluates false if the meta key is missing, is not an AxMetaKptsDetection, the keypoint
 * list is empty, an index is out of range, or any selected keypoint's visibility is
 * less than or equal to the threshold. The keypoint count defaults to 17 when the shape
 * is empty.
 */
class KptsConfidencePredicate : public Predicate {
public:
    /**
     * Args:
     *     meta_key (std::string): Key of the keypoint meta in Frame::meta.
     *     indices (std::vector<int>): Keypoint indices that must pass.
     *     min_confidence (float): Exclusive lower bound on each keypoint's visibility.
     */
    KptsConfidencePredicate(std::string meta_key, std::vector<int> indices, float min_confidence)
        : meta_key_(std::move(meta_key)), indices_(std::move(indices)), min_confidence_(min_confidence)
    {}

    bool eval(const Frame &frame) const override
    {
        auto it = frame.meta.find(meta_key_);
        if (it == frame.meta.end()) return false;
        auto *kd = dynamic_cast<AxMetaKptsDetection *>(it->second.get());
        if (!kd) return false;

        try {
            const auto kshape = kd->get_kpts_shape();
            const size_t n_kpts = kshape.empty() ? 17u : static_cast<size_t>(kshape[0]);
            if (n_kpts == 0) return false;
            const auto kpts = kd->get_kpts_xyv(0, n_kpts);
            for (int idx : indices_) {
                if (idx < 0 || static_cast<size_t>(idx) >= kpts.size()) return false;
                if (kpts[idx].visibility <= min_confidence_) return false;
            }
            return true;
        } catch (const std::out_of_range &) {
            return false;
        }
    }

private:
    std::string meta_key_;
    std::vector<int> indices_;
    float min_confidence_;
};

/**
 * Predicate implemented by a shared library loaded with dlopen.
 *
 * The library must export `ax_create_predicate` (called with a null argument) and
 * `ax_destroy_predicate`. The library is closed on destruction.
 *
 * Note:
 *     Not copyable. The plugin must be built against the same Frame layout.
 */
class PluginPredicate : public Predicate {
public:
    /**
     * Load the plugin and create its predicate.
     *
     * Args:
     *     so_path (const std::string &): Path to the shared library.
     *
     * Raises:
     *     std::runtime_error: If dlopen fails, a symbol is missing, or creation returns null.
     */
    explicit PluginPredicate(const std::string &so_path)
    {
        handle_ = dlopen(so_path.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!handle_) {
            throw std::runtime_error(
                "PluginPredicate: dlopen failed for '" + so_path + "': " + dlerror());
        }
        using CreateFn = Predicate *(*)(const char *);
        auto create_fn = reinterpret_cast<CreateFn>(dlsym(handle_, "ax_create_predicate"));
        destroy_fn_ = reinterpret_cast<void (*)(Predicate *)>(
            dlsym(handle_, "ax_destroy_predicate"));
        if (!create_fn || !destroy_fn_) {
            dlclose(handle_);
            throw std::runtime_error(
                "PluginPredicate: '" + so_path +
                "' is missing ax_create_predicate/ax_destroy_predicate");
        }
        impl_ = create_fn(nullptr);
        if (!impl_) {
            dlclose(handle_);
            throw std::runtime_error(
                "PluginPredicate: ax_create_predicate returned null for '" + so_path + "'");
        }
    }

    ~PluginPredicate() override
    {
        if (impl_ && destroy_fn_) destroy_fn_(impl_);
        if (handle_) dlclose(handle_);
    }

    PluginPredicate(const PluginPredicate &) = delete;
    PluginPredicate &operator=(const PluginPredicate &) = delete;

    bool eval(const Frame &frame) const override { return impl_->eval(frame); }

private:
    void *handle_ = nullptr;
    Predicate *impl_ = nullptr;
    void (*destroy_fn_)(Predicate *) = nullptr;
};

}
