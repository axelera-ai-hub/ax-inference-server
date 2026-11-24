/**
 * Client-side player for the pinned benchmark stream dialog.
 *
 * Reads a multipart JPEG stream (`--frame` boundaries, optional `X-Capture-Ts` header per part) with
 * `fetch`, buffers frames, and replays them at their capture-time spacing shifted by
 * `window.__pinnedStreamPlaybackDelayMs`, so playback is smooth despite network jitter.
 *
 * Entry points: `window.__pinnedStreamStart(imgId, url)` and `window.__pinnedStreamStop(imgId)`.
 * Optional DOM elements `<imgId>-spinner` and `<imgId>-status` show buffering state.
 */

// No new frame for this long (ms) while the queue is empty puts the player back into rebuffering.
const PINNED_STREAM_STALL_MS = 800;

// Rate at which the playback timer checks for frames that are due.
const PINNED_STREAM_TARGET_FPS = 30;
const PINNED_STREAM_TICK_MS = 1000 / PINNED_STREAM_TARGET_FPS;

// Cap on buffered frames; the oldest are dropped beyond this.
const PINNED_STREAM_MAX_QUEUED_FRAMES = 300;

/**
 * Start (or restart) playing the stream at `url` into the `<img>` with id `imgId`.
 *
 * Phases: 'buffering' until the playback delay has elapsed since the first frame, 'playing', and
 * 'rebuffering' when frames stop arriving. Per-stream state is kept in `window.__pinnedStreams[imgId]`.
 */
window.__pinnedStreamStart = function(imgId, url) {
    window.__pinnedStreamStop(imgId);
    const img = document.getElementById(imgId);
    if (!img) return;
    const spinner = document.getElementById(imgId + '-spinner');
    const statusEl = document.getElementById(imgId + '-status');
    window.__pinnedStreams = window.__pinnedStreams || {};
    const state = {
        aborted: false, phase: 'buffering', queue: [], shownUrl: null, reader: null,
        tickTimer: null, lastFrameAt: Date.now(),
        anchorCaptureTsMs: null, anchorReceiveMs: null,
        pendingUrl: null, decoding: false,
    };
    window.__pinnedStreams[imgId] = state;
    if (spinner) spinner.style.display = 'flex';
    if (statusEl) statusEl.textContent = 'Buffering live stream…';

    const MARKER = new TextEncoder().encode('--frame\r\n');
    let buf = new Uint8Array(0);

    /** Return the index of the next `--frame` marker in `buf` at or after `from`, or -1. */
    function findMarker(from) {
        outer:
        for (let i = from; i <= buf.length - MARKER.length; i++) {
            for (let j = 0; j < MARKER.length; j++) {
                if (buf[i + j] !== MARKER[j]) continue outer;
            }
            return i;
        }
        return -1;
    }

    /** Return the index of the next blank line (CRLF CRLF) ending a part header at or after `from`, or -1. */
    function findHeaderEnd(from) {
        for (let i = from; i <= buf.length - 4; i++) {
            if (buf[i] === 13 && buf[i + 1] === 10 && buf[i + 2] === 13 && buf[i + 3] === 10) return i;
        }
        return -1;
    }

    /**
     * Queue a decoded part for playback.
     * The first frame anchors the capture clock to the local receive time; each frame is due at
     * anchor + (its capture time - anchor capture time) + delay. Without a capture timestamp it is due
     * `delay` after arrival.
     */
    function enqueueFrame(jpegBytes, captureTsMs) {
        const nowMs = Date.now();
        if (state.anchorReceiveMs === null) {
            state.anchorCaptureTsMs = captureTsMs !== null ? captureTsMs : nowMs;
            state.anchorReceiveMs = nowMs;
        }
        const delayMs = Math.max(0, window.__pinnedStreamPlaybackDelayMs || 0);
        const targetPresentMs = captureTsMs !== null
            ? state.anchorReceiveMs + (captureTsMs - state.anchorCaptureTsMs) + delayMs
            : nowMs + delayMs;
        const frameUrl = URL.createObjectURL(new Blob([jpegBytes], {type: 'image/jpeg'}));
        state.queue.push({url: frameUrl, targetPresentMs});
        while (state.queue.length > PINNED_STREAM_MAX_QUEUED_FRAMES) {
            URL.revokeObjectURL(state.queue.shift().url);
        }
        state.lastFrameAt = nowMs;
    }

    /**
     * Read the next chunk from the response, append it to `buf` and extract every complete frame
     * (marker, header, JPEG body up to the next marker), then continue reading until the stream ends.
     */
    function pump() {
        state.reader.read().then(({done, value}) => {
            if (state.aborted || done) return;
            const merged = new Uint8Array(buf.length + value.length);
            merged.set(buf, 0);
            merged.set(value, buf.length);
            buf = merged;
            while (true) {
                const start = findMarker(0);
                if (start < 0) break;
                const headerStart = start + MARKER.length;
                const headerEnd = findHeaderEnd(headerStart);
                if (headerEnd < 0) break;
                const dataStart = headerEnd + 4;
                const next = findMarker(dataStart);
                if (next < 0) break;
                let dataEnd = next;
                if (buf[dataEnd - 2] === 13 && buf[dataEnd - 1] === 10) dataEnd -= 2;
                const headerText = new TextDecoder().decode(buf.slice(headerStart, headerEnd));
                const jpegBytes = buf.slice(dataStart, dataEnd);
                buf = buf.slice(next);
                const m = /X-Capture-Ts:\s*(\d+)/i.exec(headerText);
                enqueueFrame(jpegBytes, m ? parseInt(m[1], 10) : null);
            }
            pump();
        }).catch(() => {});
    }

    fetch(url, {cache: 'no-store'}).then(resp => {
        if (state.aborted) { resp.body.cancel(); return; }
        state.reader = resp.body.getReader();
        pump();
    }).catch(() => {});

    /** Set the frame as the image source and free the previously shown frame once the new one has loaded. */
    function presentFrame(frameUrl) {
        const oldUrl = state.shownUrl;
        img.onload = () => { if (oldUrl) URL.revokeObjectURL(oldUrl); };
        img.src = frameUrl;
        state.shownUrl = frameUrl;
    }

    /**
     * Decode the pending frame off-screen and then present it, so the visible image never shows a
     * half-decoded frame. Frames that fail to decode are skipped; runs until no frame is pending.
     */
    async function decodeAndPresentLoop() {
        state.decoding = true;
        while (state.pendingUrl !== null && !state.aborted) {
            const url = state.pendingUrl;
            state.pendingUrl = null;
            const probe = new Image();
            probe.src = url;
            try {
                await probe.decode();
            } catch (e) {
                URL.revokeObjectURL(url);
                continue;
            }
            if (state.aborted) { URL.revokeObjectURL(url); break; }
            presentFrame(url);
        }
        state.decoding = false;
    }

    /** Make a frame the pending one (dropping any pending frame not yet shown) and start the decode loop if idle. */
    function displayFrame(frameUrl) {
        if (state.pendingUrl !== null) URL.revokeObjectURL(state.pendingUrl);
        state.pendingUrl = frameUrl;
        if (!state.decoding) decodeAndPresentLoop();
    }

    /** Drop queued frames, reset the time anchor and show the spinner while waiting for new frames. */
    function enterRebuffering() {
        state.phase = 'rebuffering';
        for (const frame of state.queue) URL.revokeObjectURL(frame.url);
        state.queue = [];
        state.anchorCaptureTsMs = null;
        state.anchorReceiveMs = null;
        if (spinner) spinner.style.display = 'flex';
    }

    // Playback tick: while (re)buffering, update the status text and switch to 'playing' once the delay
    // has elapsed; otherwise show the newest due frame and rebuffer after a stall.
    state.tickTimer = setInterval(() => {
        const nowMs = Date.now();
        const delayMs = Math.max(0, window.__pinnedStreamPlaybackDelayMs || 0);
        if (state.phase === 'buffering' || state.phase === 'rebuffering') {
            const verb = state.phase === 'buffering' ? 'Buffering live stream' : 'Waiting for new frames';
            if (state.anchorReceiveMs !== null) {
                const elapsedMs = nowMs - state.anchorReceiveMs;
                if (statusEl) {
                    statusEl.textContent =
                        `${verb}… ${(Math.min(elapsedMs, delayMs) / 1000).toFixed(1)} / ${(delayMs / 1000).toFixed(1)}s`;
                }
                if (elapsedMs >= delayMs) {
                    state.phase = 'playing';
                    if (spinner) spinner.style.display = 'none';
                }
            } else if (statusEl) {
                statusEl.textContent = `${verb}…`;
            }
            return;
        }
        let shown = null;
        while (state.queue.length > 0 && state.queue[0].targetPresentMs <= nowMs) {
            const frame = state.queue.shift();
            if (shown) URL.revokeObjectURL(shown.url);
            shown = frame;
        }
        if (shown) displayFrame(shown.url);
        if (state.queue.length === 0 && nowMs - state.lastFrameAt > PINNED_STREAM_STALL_MS) {
            enterRebuffering();
        }
    }, PINNED_STREAM_TICK_MS);
};

/** Stop the stream for `imgId`: cancel the reader and timer, free all frame URLs, clear the image and hide the spinner. */
window.__pinnedStreamStop = function(imgId) {
    const state = (window.__pinnedStreams || {})[imgId];
    if (!state) return;
    state.aborted = true;
    if (state.tickTimer) clearInterval(state.tickTimer);
    if (state.reader) { try { state.reader.cancel(); } catch (e) {} }
    for (const frame of state.queue) URL.revokeObjectURL(frame.url);
    if (state.shownUrl) URL.revokeObjectURL(state.shownUrl);
    if (state.pendingUrl) URL.revokeObjectURL(state.pendingUrl);
    delete window.__pinnedStreams[imgId];
    const img = document.getElementById(imgId);
    if (img) img.src = '';
    const spinner = document.getElementById(imgId + '-spinner');
    if (spinner) spinner.style.display = 'none';
};
