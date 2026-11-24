
// Asynchronous file logger built on io_uring.
// Exposes the process-wide IoUringLogger singleton; messages are written to a log file
// without blocking the caller on disk I/O.
#pragma once
#include <liburing.h>
#include <fcntl.h>
#include <unistd.h>
#include <cstring>
#include <cstdio>
#include <vector>
#include <atomic>
#include <mutex>
#include <thread>
#include <chrono>
#include <string>

/**
 * Process-wide asynchronous logger that writes timestamped lines to a file through io_uring.
 *
 * Each message is copied into a slot of a fixed buffer pool and submitted as an io_uring
 * write. A reaper thread reaps completions and returns the slot to the pool. When no slot or
 * submission entry is available the message is dropped and counted rather than blocking the
 * caller. If the log file or the ring cannot be set up, the logger is disabled and every
 * log call is a no-op.
 *
 * Note:
 *   Thread-safe: log() and logf() may be called from any thread. Access the logger through
 *   instance(); copying is deleted.
 *
 * Environment:
 *   URING_LOG_PATH (string): Log file path. Default "./axinferencenet_uring.log".
 *   URING_BUFFER_COUNT (int): Number of buffer slots, clamped to [16, 1024]. Default 128.
 */
class IoUringLogger {
public:
    /** Submission/completion queue size passed to io_uring_queue_init. */
    static constexpr size_t RING_SIZE = 256;
    /** Default number of buffer slots (see URING_BUFFER_COUNT). */
    static constexpr size_t DEFAULT_BUFFER_COUNT = 128;
    /** Size in bytes of each buffer slot; longer messages are truncated to BUFFER_SIZE - 1. */
    static constexpr size_t BUFFER_SIZE = 4096;

    /**
     * Get the process-wide logger, constructing it on first use.
     *
     * Returns:
     *   IoUringLogger&: The singleton instance.
     */
    static IoUringLogger& instance() {
        static IoUringLogger logger;
        return logger;
    }

    /**
     * Open the log file, set up the io_uring ring and buffer pool, and start the reaper thread.
     *
     * On failure to open the file or initialise the ring, prints an error to stderr and leaves
     * the logger disabled. On success prints a one-line summary to stdout.
     */
    IoUringLogger() {
        const char* log_path_env = std::getenv("URING_LOG_PATH");
        std::string log_path = log_path_env ? log_path_env : "./axinferencenet_uring.log";

        log_fd_ = open(log_path.c_str(), O_WRONLY | O_CREAT | O_APPEND, 0644);
        if (log_fd_ < 0) {
            fprintf(stderr, "[IoUringLogger] ERROR: Failed to open %s: %s\n",
                    log_path.c_str(), strerror(errno));
            enabled_ = false;
            return;
        }

        const char* buffer_count_env = std::getenv("URING_BUFFER_COUNT");
        buffer_count_ = buffer_count_env ? std::atoi(buffer_count_env) : DEFAULT_BUFFER_COUNT;
        if (buffer_count_ < 16) buffer_count_ = 16;
        if (buffer_count_ > 1024) buffer_count_ = 1024;

        int ret = io_uring_queue_init(RING_SIZE, &ring_, 0);
        if (ret < 0) {
            fprintf(stderr, "[IoUringLogger] ERROR: io_uring_queue_init failed: %s\n",
                    strerror(-ret));
            close(log_fd_);
            enabled_ = false;
            return;
        }

        buffers_.reserve(buffer_count_);
        for (size_t i = 0; i < buffer_count_; ++i) {
            Buffer buf;
            buf.data.resize(BUFFER_SIZE);
            buf.in_use.store(false, std::memory_order_relaxed);
            buffers_.push_back(std::move(buf));
        }

        enabled_ = true;
        fprintf(stdout, "[IoUringLogger] Initialized: fd=%d, ring_size=%zu, buffers=%zu, path=%s\n",
                log_fd_, RING_SIZE, buffer_count_, log_path.c_str());

        reaper_running_ = true;
        reaper_thread_ = std::thread(&IoUringLogger::ReaperLoop, this);

        log("URING", "=== IoUringLogger Active ===\n");
    }

    /**
     * Flush and shut down the logger.
     *
     * Logs a shutdown line, stops the reaper thread, submits and drains pending completions,
     * closes the ring and file, and prints submission, completion and drop counts to stdout.
     * Does nothing if the logger is disabled.
     */
    ~IoUringLogger() {
        if (!enabled_) return;

        log("URING", "=== IoUringLogger Shutting Down ===\n");

        reaper_running_ = false;
        if (reaper_thread_.joinable()) {
            reaper_thread_.join();
        }

        {
            std::lock_guard<std::mutex> lock(ring_mutex_);
            io_uring_submit(&ring_);
            struct io_uring_cqe* cqe;
            while (io_uring_peek_cqe(&ring_, &cqe) == 0) {
                io_uring_cqe_seen(&ring_, cqe);
            }
        }

        io_uring_queue_exit(&ring_);
        close(log_fd_);

        uint64_t drops = drops_.load();
        fprintf(stdout, "[IoUringLogger] Stats: submissions=%lu, completions=%lu, drops=%lu\n",
                submissions_.load(), completions_.load(), drops);
        if (drops > 0) {
            fprintf(stdout, "[IoUringLogger] WARNING: %lu log messages were dropped\n", drops);
        }
    }

    /**
     * Write one timestamped line to the log file.
     *
     * The line is formatted as "[HH:MM:SS.uuuuuu] [category] msg" in local time. The message is
     * not newline-terminated automatically, so callers include "\n" themselves. The message is
     * dropped (and counted) if every buffer slot is in use or no submission entry is available.
     *
     * Args:
     *   category (const char*): Short tag such as "PIPELINE" or "STARTUP".
     *   msg (const std::string&): Message text; truncated to BUFFER_SIZE - 1 bytes in total.
     */
    void log(const char* category, const std::string& msg) {
        if (!enabled_) return;

        size_t buf_idx = next_buffer_.fetch_add(1, std::memory_order_relaxed) % buffer_count_;

        int spin_count = 0;
        while (buffers_[buf_idx].in_use.load(std::memory_order_acquire)) {
            buf_idx = (buf_idx + 1) % buffer_count_;
            if (++spin_count > buffer_count_ * 2) {
                drops_.fetch_add(1, std::memory_order_relaxed);
                return;
            }
        }

        buffers_[buf_idx].in_use.store(true, std::memory_order_release);

        auto now = std::chrono::system_clock::now();
        auto us = std::chrono::duration_cast<std::chrono::microseconds>(
            now.time_since_epoch()) % 1000000;
        auto t = std::chrono::system_clock::to_time_t(now);
        struct tm tm_info;
        localtime_r(&t, &tm_info);

        char timestamp[32];
        snprintf(timestamp, sizeof(timestamp), "[%02d:%02d:%02d.%06ld] ",
                tm_info.tm_hour, tm_info.tm_min, tm_info.tm_sec, us.count());

        std::string full_msg = std::string(timestamp) + "[" + category + "] " + msg;
        size_t len = std::min(full_msg.size(), BUFFER_SIZE - 1);
        memcpy(buffers_[buf_idx].data.data(), full_msg.c_str(), len);
        buffers_[buf_idx].len = len;

        std::lock_guard<std::mutex> lock(ring_mutex_);

        struct io_uring_sqe* sqe = io_uring_get_sqe(&ring_);
        if (!sqe) {
            buffers_[buf_idx].in_use.store(false, std::memory_order_release);
            drops_.fetch_add(1, std::memory_order_relaxed);
            return;
        }

        io_uring_prep_write(sqe, log_fd_, buffers_[buf_idx].data.data(), len, -1);
        io_uring_sqe_set_data(sqe, reinterpret_cast<void*>(buf_idx));
        io_uring_submit(&ring_);

        submissions_.fetch_add(1, std::memory_order_relaxed);
    }

    /**
     * Write a printf-style formatted line to the log file.
     *
     * With no format arguments the format string is logged verbatim (no printf processing).
     * Otherwise the message is formatted into a 4096-byte stack buffer and truncated if longer.
     *
     * Args:
     *   category (const char*): Short tag such as "PIPELINE" or "STARTUP".
     *   format (const char*): printf-style format string.
     *   args: Values for the format conversions.
     */
    template<typename... Args>
    void logf(const char* category, const char* format, Args... args) {
        if constexpr (sizeof...(Args) == 0) {
            log(category, format);
        } else {
            char buffer[4096];
            snprintf(buffer, sizeof(buffer), format, args...);
            log(category, buffer);
        }
    }

private:
    /**
     * Reaper thread body: reap io_uring completions and release the matching buffer slots.
     *
     * Polls without blocking and sleeps briefly when the completion queue is empty. Exits when
     * reaper_running_ is cleared, or after 10 consecutive unexpected errors, in which case
     * slots are no longer recycled and later messages are eventually dropped.
     */
    void ReaperLoop() {
        int consecutive_errors = 0;
        const int MAX_CONSECUTIVE_ERRORS = 10;

        while (reaper_running_) {
            struct io_uring_cqe* cqe;
            int ret;
            {
                std::lock_guard<std::mutex> lock(ring_mutex_);
                ret = io_uring_peek_cqe(&ring_, &cqe);
            }

            if (ret == 0) {
                consecutive_errors = 0;
                size_t buf_idx = reinterpret_cast<size_t>(io_uring_cqe_get_data(cqe));
                buffers_[buf_idx].in_use.store(false, std::memory_order_release);
                {
                    std::lock_guard<std::mutex> lock(ring_mutex_);
                    io_uring_cqe_seen(&ring_, cqe);
                }
                completions_.fetch_add(1, std::memory_order_relaxed);
            } else if (ret == -EINTR) {
                continue;
            } else if (ret == -EAGAIN || ret == -EBUSY) {
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
                continue;
            } else if (ret < 0) {
                consecutive_errors++;
                if (reaper_running_) {
                    fprintf(stderr, "[IoUringLogger] Reaper error #%d: %s (ret=%d)\n",
                            consecutive_errors, strerror(-ret), ret);
                }

                if (consecutive_errors >= MAX_CONSECUTIVE_ERRORS) {
                    fprintf(stderr, "[IoUringLogger] FATAL: Reaper hit %d consecutive errors, exiting\n",
                            MAX_CONSECUTIVE_ERRORS);
                    break;
                }

                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
        }

        fprintf(stderr, "[IoUringLogger] Reaper thread exiting (reaper_running=%d, errors=%d)\n",
                reaper_running_.load(), consecutive_errors);
    }

    /**
     * One slot of the buffer pool.
     *
     * Attributes:
     *   data (std::vector<char>): Storage of BUFFER_SIZE bytes holding the formatted line.
     *   len (size_t): Number of valid bytes in data.
     *   in_use (std::atomic<bool>): True from claim until the write completion is reaped.
     *
     * Note:
     *   Movable so it can live in a std::vector; the atomic flag is copied on move.
     */
    struct Buffer {
        std::vector<char> data;
        size_t len = 0;
        std::atomic<bool> in_use{false};

        Buffer() = default;
        Buffer(Buffer&& other) noexcept
            : data(std::move(other.data)), len(other.len),
              in_use(other.in_use.load(std::memory_order_relaxed)) {}
        Buffer& operator=(Buffer&& other) noexcept {
            if (this != &other) {
                data = std::move(other.data);
                len = other.len;
                in_use.store(other.in_use.load(std::memory_order_relaxed),
                            std::memory_order_relaxed);
            }
            return *this;
        }
        Buffer(const Buffer&) = delete;
        Buffer& operator=(const Buffer&) = delete;
    };

    // File descriptor of the log file; -1 until opened.
    int log_fd_ = -1;
    struct io_uring ring_;
    // Serialises access to ring_ (submission and completion handling).
    std::mutex ring_mutex_;
    std::vector<Buffer> buffers_;
    size_t buffer_count_ = 0;
    // Monotonic counter used to pick the starting slot for each message.
    std::atomic<size_t> next_buffer_{0};
    std::atomic<uint64_t> submissions_{0};
    std::atomic<uint64_t> completions_{0};
    std::atomic<uint64_t> drops_{0};
    bool enabled_ = false;

    std::thread reaper_thread_;
    std::atomic<bool> reaper_running_{false};

    IoUringLogger(const IoUringLogger&) = delete;
    IoUringLogger& operator=(const IoUringLogger&) = delete;
};