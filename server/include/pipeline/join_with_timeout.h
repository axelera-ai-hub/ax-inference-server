
#pragma once

// Helper to join a std::thread with a deadline, abandoning it if it does not finish.

#include <chrono>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

#include "common/io_uring_logger.hpp"

namespace Ax {

/**
 * State shared between join_with_timeout() and its detached joiner thread.
 *
 * Attributes:
 *     m: Guards done.
 *     cv: Signalled when done becomes true.
 *     done: Set by the joiner thread after the target has been joined.
 */
struct JoinState {
    std::mutex m;
    std::condition_variable cv;
    bool done = false;
};

/**
 * Join a thread, waiting at most the given timeout.
 *
 * The thread is moved into a detached helper that performs the blocking join. If the
 * timeout expires the helper (and the target thread) is left running and a message is
 * logged, so shutdown and restart can proceed.
 *
 * Args:
 *     target (std::thread &): Thread to join; left non-joinable after the call.
 *     timeout (std::chrono::milliseconds): Maximum time to wait.
 *     label (const std::string &): Name used in the log message on timeout.
 *
 * Returns:
 *     bool: True if the thread was joined (or was not joinable), false on timeout.
 */
inline bool
join_with_timeout(std::thread &target, std::chrono::milliseconds timeout,
                  const std::string &label)
{
    if (!target.joinable()) return true;

    auto state = std::make_shared<JoinState>();
    auto thread_ptr = std::make_shared<std::thread>(std::move(target));

    std::thread joiner([thread_ptr, state]() {
        thread_ptr->join();
        std::lock_guard<std::mutex> lk(state->m);
        state->done = true;
        state->cv.notify_all();
    });
    joiner.detach();

    std::unique_lock<std::mutex> lk(state->m);
    bool joined = state->cv.wait_for(lk, timeout, [&state] { return state->done; });
    if (!joined) {
        IoUringLogger::instance().logf("PIPELINE",
            "join_with_timeout: %s did not exit within %ldms — abandoning it "
            "(thread leak accepted to guarantee shutdown/restart completes)\n",
            label.c_str(), static_cast<long>(timeout.count()));
    }
    return joined;
}

}
