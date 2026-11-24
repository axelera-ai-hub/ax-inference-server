
// Pipeline node that renames one meta key.
#pragma once

#include <string>
#include <utility>

#include "pipeline/node.h"

namespace Ax {

/**
 * Moves a meta entry from one key to another and forwards the frame.
 *
 * If the source key is absent the frame is forwarded unchanged. An existing entry under the
 * destination key is overwritten.
 */
class RenameNode : public AxPipelineNode {
public:
    /**
     * Create the node.
     *
     * Args:
     *   from_key (std::string): Meta key to move.
     *   to_key (std::string): New meta key.
     */
    RenameNode(std::string from_key, std::string to_key)
        : from_key_(std::move(from_key)), to_key_(std::move(to_key))
    {}

    /**
     * Rename the meta entry and forward the frame.
     *
     * Args:
     *   frame (std::shared_ptr<Frame>): Frame to modify in place.
     */
    void process(std::shared_ptr<Frame> frame) override
    {
        auto it = frame->meta.find(from_key_);
        if (it != frame->meta.end()) {
            frame->meta[to_key_] = std::move(it->second);
            frame->meta.erase(it);
        }
        if (next_) next_(std::move(frame));
    }

private:
    std::string from_key_;
    std::string to_key_;
};

}
