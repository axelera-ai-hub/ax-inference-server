
#pragma once

// Bounded-wait push for BlockingQueue.

#include <chrono>
#include <mutex>

#include "AxStreamerUtils.hpp"

namespace Ax {

/**
 * Push an item into a BlockingQueue, waiting up to a timeout for free space.
 *
 * Args:
 *     q (BlockingQueue<T> &): Destination queue.
 *     item (T &): Item to push; moved from only on success.
 *     timeout (std::chrono::milliseconds): Maximum time to wait for space.
 *
 * Returns:
 *     bool: True if pushed, false on timeout or if the queue is stopped.
 */
template <typename T>
bool
try_push_for(BlockingQueue<T> &q, T &item, std::chrono::milliseconds timeout)
{
    std::unique_lock<std::mutex> lock(q.mutex);
    const bool have_space = q.full_condition.wait_for(
        lock, timeout, [&q] { return q.queue.size() < q.queue_depth || !q.running; });
    if (!have_space || !q.running) {
        return false;
    }
    q.queue.push(std::move(item));
    lock.unlock();
    q.empty_condition.notify_one();
    return true;
}

}
