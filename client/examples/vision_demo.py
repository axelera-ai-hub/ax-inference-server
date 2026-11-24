"""Stream an image or video through vision pipelines with concurrent streams and report fps and latency.

Optionally tracks detections and writes one annotated mp4 canvas that tiles every stream.

Note:
    Streams are split over client processes (one per STREAMS_PER_WORKER streams by default) that share the canvas and live fps through shared memory.
"""


from __future__ import annotations

import argparse
import asyncio
import collections
import math
import multiprocessing
import os
import queue as queue_mod
import subprocess
import sys
import threading
import time
from multiprocessing import shared_memory
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1]
for sub in ('', 'tracker'):
    sys.path.insert(0, str(CLIENT / sub) if sub else str(CLIENT))

import cv2
import numpy as np

cv2.setNumThreads(1)

from adapters.common.rendering import (
    cell_rects, draw_detections, draw_tracks, grid_layout, letterbox, load_logo, overlay_logo, parse_canvas_size, put_label)
from adapters.image_cv import ImageAdapterCV
from adapters.video_file_cv import VideoFileAdapterCV
from inference import AsyncAxVisionClient

LOGO = CLIENT / 'ui' / 'gui' / 'static' / 'axelera_inference_server_watermark.png'
LOGO_WIDTH_FRACTION = 0.2
WINDOW_S = 1.0
LIVE_EVERY_S = 5.0
INFLIGHT_PER_STREAM = 2
RENDER_THREADS = 4
STREAMS_PER_WORKER = 11
RENDER_BACKLOG = 3
IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.bmp'}


def parse_args(argv=None):
    """Parse the command-line arguments."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--endpoints', required=True, help='pipeline endpoints host:port[,host:port...]; requests spread over all of them')
    p.add_argument('--streams', type=int, default=1, help='number of concurrent streams (default 1)')
    p.add_argument('--source', required=True, help='image or video file; every stream plays it')
    p.add_argument('--frames', type=int, default=0, help='frames per stream (default: a video once through, an image 100)')
    p.add_argument('--fps', type=float, default=0, help="frame rate each stream is fed at, also the canvas video's rate "
                   "(default 0: the source's own rate, feeding as fast as results come back)")
    p.add_argument('--concurrency', type=int, default=0, help="the client's in-flight request limit (default: 4 per stream, at least 8)")
    p.add_argument('--inflight', type=int, default=INFLIGHT_PER_STREAM, help='frames each stream keeps submitted to the server at once '
                   '(default %(default)s). Inference queueing, not rendering: more in flight can raise fps when the server is idle, '
                   'but at saturation it only adds queueing latency (about streams x inflight / total fps)')
    p.add_argument('--workers', type=int, default=0, help='client processes the streams are split over, each with its own client and GIL '
                   '(default 0: one per %d streams). One process tops out around 600 fps' % STREAMS_PER_WORKER)
    p.add_argument('--output', help='annotated mp4 (H.264): one canvas with every stream')
    p.add_argument('--canvas', default='480p', help='canvas size: 360p, 480p, 720p, 1080p, 1440p, 2160p or WxH (default 480p)')
    p.add_argument('--grid', help='tile grid COLSxROWS holding all streams (default: the smallest near-square grid, 12 -> 4x3)')
    p.add_argument('--track', action='store_true', help='track detections across frames (AxTrack) and draw track ids')
    return p.parse_args(argv)


def make_adapter(path: str):
    """Open an image file or a video file (played once, no loop) as a frame adapter."""
    if Path(path).suffix.lower() in IMAGE_SUFFIXES:
        return ImageAdapterCV(path)
    return VideoFileAdapterCV(path, loop=False)


def pct(values, q: float) -> float:
    """Compute a percentile by the nearest-rank method.

    Args:
        values: Samples, in any order.
        q (float): Percentile, 0 to 100.

    Returns:
        float: The percentile, or 0.0 if there are no samples.
    """
    if not values:
        return 0.0
    v = sorted(values)
    return float(v[min(len(v) - 1, max(0, int(np.ceil(q / 100 * len(v))) - 1))])


def per_second(times: list[float], start: float, end: float) -> list[float]:
    """Count completions per whole second of a run.

    Args:
        times (list[float]): Completion timestamps (time.monotonic).
        start (float): Run start.
        end (float): Run end.

    Returns:
        list[float]: Frames completed in each whole second. For runs shorter than 2 seconds, a single overall rate.
    """
    seconds = int(end - start)
    if seconds < 2:
        return [len(times) / max(end - start, 1e-6)] if times else []
    bins = [0] * seconds
    for t in times:
        i = int(t - start)
        if i < seconds:
            bins[i] += 1
    return [float(b) for b in bins]


def release(shm: shared_memory.SharedMemory, unlink: bool = False) -> None:
    """Close a shared memory block and optionally unlink it.

    A BufferError from close (a view still exists) is ignored.

    Args:
        shm (shared_memory.SharedMemory): The block.
        unlink (bool, optional): Also remove the block; only the creating process should. Defaults to False.
    """
    try:
        shm.close()
    except BufferError:
        pass
    if unlink:
        shm.unlink()


class VideoSink:
    """Writer that pipes raw BGR frames into an ffmpeg process producing an H.264 mp4.

    Needs imageio-ffmpeg for the ffmpeg binary.
    """
    def __init__(self, path: str, width: int, height: int, fps: float):
        """Start ffmpeg.

        Args:
            path (str): Output mp4 path.
            width (int): Frame width in pixels.
            height (int): Frame height in pixels.
            fps (float): Output frame rate.
        """
        import imageio_ffmpeg
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{width}x{height}',
               '-r', f'{fps:g}', '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p',
               '-movflags', '+faststart', path]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def write(self, frame: np.ndarray) -> None:
        """Send one BGR frame of the configured size to ffmpeg."""
        self.proc.stdin.write(frame.tobytes())

    def close(self) -> None:
        """Close ffmpeg input, wait for it to finish and warn on a non-zero exit."""
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            print('WARNING: ffmpeg reported an error while encoding', file=sys.stderr)


def canvas_geometry(streams: int, size: str, grid: str | None) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """Compute the canvas size and the tile rectangle of each stream.

    Args:
        streams (int): Number of streams.
        size (str): Canvas size name or WxH.
        grid (str | None): COLSxROWS, or None for the smallest near-square grid.

    Returns:
        tuple[int, int, list[tuple[int, int, int, int]]]: Width and height (both rounded down to even for H.264) and one (x, y, w, h) per stream.
    """
    width, height = parse_canvas_size(size)
    width, height = width - width % 2, height - height % 2
    return width, height, cell_rects(width, height, *grid_layout(streams, grid))


class Canvas:
    """The annotated output video: one frame tiling every stream, plus a logo and a total-fps label.

    The frame lives in shared memory so worker processes can draw their tiles into it; the parent process encodes it at a fixed rate.

    Attributes:
        width (int): Frame width in pixels.
        height (int): Frame height in pixels.
        rects (list[tuple[int, int, int, int]]): Tile (x, y, w, h) per stream.
        fps (float): Output frame rate.
        live: Shared array of per-stream live fps, summed for the label.
        shm (shared_memory.SharedMemory): Backing store of the frame.
        frames_written (int): Frames encoded so far; final after `run` ends.

    Raises:
        RuntimeError: On construction, if the logo is missing or not an RGBA png.
    """
    def __init__(self, path: str, streams: int, size: str, grid: str | None, fps: float, live):
        """Create the shared frame and start the video sink.

        Args:
            path (str): Output mp4 path.
            streams (int): Number of streams.
            size (str): Canvas size name or WxH.
            grid (str | None): COLSxROWS, or None for the default grid.
            fps (float): Output frame rate.
            live: Shared array of per-stream live fps.
        """
        self.width, self.height, self.rects = canvas_geometry(streams, size, grid)
        self.fps = fps
        self.live = live
        self.logo = load_logo(str(LOGO), max(24, round(self.width * LOGO_WIDTH_FRACTION)))
        if self.logo is None:
            raise RuntimeError(f'logo missing or not an RGBA png: {LOGO}')
        self.shm = shared_memory.SharedMemory(create=True, size=self.width * self.height * 3)
        self.view = np.ndarray((self.height, self.width, 3), np.uint8, buffer=self.shm.buf)
        self.view[:] = 0
        self.sink = VideoSink(path, self.width, self.height, fps)
        self.label_scale = max(0.5, self.height / 900)
        self.frames_written = 0

    def compose(self) -> np.ndarray:
        """Return a copy of the current frame with the total-fps label and logo drawn on it."""
        frame = self.view.copy()
        put_label(frame, f'{float(self.live.sum()):.0f} fps total', 6, self.height - 6, self.label_scale, anchor='bottom-left')
        overlay_logo(frame, self.logo, margin=max(6, self.width // 100))
        return frame

    async def run(self, stop: asyncio.Event) -> None:
        """Encode frames at a fixed rate until `stop` is set, then close the sink.

        Args:
            stop (asyncio.Event): Set to end encoding.
        """
        start, n = time.monotonic(), 0
        while not stop.is_set():
            due = start + n / self.fps
            await asyncio.sleep(max(0.0, due - time.monotonic()))
            await asyncio.to_thread(lambda: self.sink.write(self.compose()))
            n += 1
        self.frames_written = n
        self.sink.close()

    def close(self) -> None:
        """Release and unlink the shared frame."""
        release(self.shm, unlink=True)


def render_tile(raw: np.ndarray, tracked, detections, cell: tuple[int, int], label: str, scale: float) -> np.ndarray:
    """Draw detections or tracks on a frame and fit it into a tile.

    Args:
        raw (np.ndarray): The frame; drawn on in place.
        tracked: Tracks to draw, or None to draw `detections`.
        detections: Detections of the frame.
        cell (tuple[int, int]): Tile (width, height).
        label (str): Text drawn at the top left.
        scale (float): Label scale.

    Returns:
        np.ndarray: The letterboxed tile.
    """
    if tracked is not None:
        draw_tracks(raw, tracked)
    else:
        draw_detections(raw, detections)
    tile = letterbox(raw, *cell)
    put_label(tile, label, 4, 4, scale)
    return tile


def new_stats(index: int, local: int = 0) -> dict:
    """Create the stats record of one stream.

    Args:
        index (int): Global stream index.
        local (int, optional): Index within the worker process. Defaults to 0.

    Returns:
        dict: Counters and samples, with `recent` holding (time, latency ms) pairs of the last WINDOW_S seconds.
    """
    return {'stream': index, 'local': local, 'frames': 0, 'errors': 0, 'latencies': [], 'done_at': [], 'detections': 0, 'keypoints': 0, 'faces': 0, 'tracks': set(),
            'recent': collections.deque()}


class Renderer:
    """Background threads that draw frames into tiles without blocking the inference loop.

    Each stream has a small backlog (RENDER_BACKLOG); when it is full the oldest frame is dropped and counted. A stream is drawn by at most one thread at a time and streams are served round-robin. Threads run at the lowest priority where the OS allows it.

    Attributes:
        dropped (int): Frames discarded because a backlog was full.
    """
    def __init__(self, sizes: list[tuple[int, int]], place):
        """Start the render threads.

        Args:
            sizes (list[tuple[int, int]]): Tile (width, height) per local stream.
            place: Callback `place(local_index, tile)` that stores a finished tile.
        """
        self.sizes, self.place = sizes, place
        streams = len(sizes)
        self.backlog = [collections.deque(maxlen=RENDER_BACKLOG) for _ in range(streams)]
        self.busy = [False] * streams
        self.dropped = 0
        self.cursor = 0
        self.cond = threading.Condition()
        self.closing = False
        self.threads = [threading.Thread(target=self._work, daemon=True) for _ in range(RENDER_THREADS)]
        for t in self.threads:
            t.start()

    def submit(self, index: int, raw, tracked, detections, label: str) -> None:
        """Queue a frame for drawing, dropping the oldest queued frame of that stream if its backlog is full."""
        with self.cond:
            if len(self.backlog[index]) == RENDER_BACKLOG:
                self.dropped += 1
            self.backlog[index].append((raw, tracked, detections, label))
            self.cond.notify()

    def _next(self):
        """Pick the next stream with queued work that no thread is drawing.

        Returns:
            tuple | None: (stream index, queued job), or None if there is nothing to do. Marks the stream busy.
        """
        count = len(self.backlog)
        for step in range(count):
            i = (self.cursor + step) % count
            if self.backlog[i] and not self.busy[i]:
                self.busy[i] = True
                self.cursor = (i + 1) % count
                return i, self.backlog[i].popleft()
        return None

    def _work(self) -> None:
        """Render thread loop: take jobs, draw the tile, hand it to `place`, until closed."""
        try:
            os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 19)
        except (AttributeError, OSError):
            pass
        while True:
            with self.cond:
                job = self._next()
                while job is None:
                    if self.closing:
                        return
                    self.cond.wait()
                    job = self._next()
            index, (raw, tracked, detections, label) = job
            size = self.sizes[index]
            self.place(index, render_tile(raw, tracked, detections, size, label, max(0.4, size[1] / 720)))
            with self.cond:
                self.busy[index] = False
                self.cond.notify()

    def close(self) -> None:
        """Stop the threads and wait for them."""
        with self.cond:
            self.closing = True
            self.cond.notify_all()
        for t in self.threads:
            t.join()


async def run_stream(client, stats: dict, args, limit: int, fps: float, renderer: Renderer | None) -> dict:
    """Feed one stream to the server and collect its results.

    A feeder task reads frames and keeps up to `--inflight` requests submitted; this coroutine awaits the results in order, updates `stats`, tracks and queues frames for rendering. An inference error is counted and only the first is printed.

    Args:
        client: The AsyncAxVisionClient.
        stats (dict): The stream's record from new_stats.
        args (argparse.Namespace): Parsed arguments; `source_fps` must be set.
        limit (int): Maximum frames to send.
        fps (float): Rate to feed at; 0 feeds as fast as results return.
        renderer (Renderer | None): Tile renderer, or None without --output.

    Returns:
        dict: `stats`, after the stream finished.
    """
    index = stats['stream']
    tracker = None
    names: dict[int, str] = {}
    if args.track:
        from ax_track import AxTrack
        tracker = AxTrack()
    pending: asyncio.Queue = asyncio.Queue(maxsize=args.inflight)

    async def feed():
        """Read frames from the source, pace them at `fps` if set and start an inference for each."""
        with make_adapter(args.source) as adapter:
            fed = 0
            t0 = time.monotonic()
            while fed < limit:
                frame = await asyncio.to_thread(adapter.read_frame)
                if frame is None:
                    break
                if fps:
                    await asyncio.sleep(max(0.0, t0 + fed / fps - time.monotonic()))
                await pending.put((frame, time.monotonic(), asyncio.create_task(client.infer(frame.encoded))))
                fed += 1
        await pending.put(None)

    feeder = asyncio.create_task(feed())
    source_fps = args.source_fps
    while (item := await pending.get()) is not None:
        frame, sent, task = item
        try:
            result = await task
        except Exception as exc:
            stats['errors'] += 1
            if stats['errors'] == 1:
                print(f'stream {index}: inference failed: {exc}', file=sys.stderr)
            continue
        now = time.monotonic()
        latency = (now - sent) * 1000
        stats['latencies'].append(latency)
        stats['done_at'].append(now)
        stats['frames'] += 1
        stats['detections'] += len(result.detections)
        stats['keypoints'] += sum(1 for d in result.detections if len(d.keypoints) > 0)
        stats['faces'] += sum(1 for d in result.detections if d.HasField('face_bbox'))
        recent = stats['recent']
        recent.append((now, latency))
        while recent and now - recent[0][0] > WINDOW_S:
            recent.popleft()
        tracked = tracker.Track(result, timestamp=frame.sequence / (fps or source_fps)) if tracker else None
        if tracked:
            names.update({d.class_id: d.label for d in result.detections})
            for t in tracked:
                t.label = names.get(t.class_id, t.label)
            stats['tracks'].update(t.track_id for t in tracked if t.track_id >= 0)
        if renderer is not None:
            renderer.submit(stats['local'], frame.raw, tracked, result.detections,
                            f'S{index + 1} | {len(recent) / WINDOW_S:.0f} fps | {sum(ms for _, ms in recent) / len(recent):.0f} ms')
    await feeder
    return stats


async def kpi_loop(all_stats: list[dict], live_fps, live_ms, stop: asyncio.Event) -> None:
    """Refresh the shared live fps and mean latency of each stream every 0.5 s from the last WINDOW_S seconds.

    Args:
        all_stats (list[dict]): Stats of this process's streams.
        live_fps: Shared array indexed by global stream index.
        live_ms: Shared array of mean latency in ms, same indexing.
        stop (asyncio.Event): Set to end the loop.
    """
    while not stop.is_set():
        await asyncio.sleep(0.5)
        now = time.monotonic()
        for s in all_stats:
            recent = [ms for t, ms in list(s['recent']) if now - t <= WINDOW_S]
            live_fps[s['stream']] = len(recent) / WINDOW_S
            live_ms[s['stream']] = sum(recent) / len(recent) if recent else 0.0


def report(all_stats: list[dict], wall: float, track: bool, run_start: float, run_end: float) -> None:
    """Print the per-stream table, the totals and a one-line summary.

    Args:
        all_stats (list[dict]): Stats of every stream.
        wall (float): Run duration in seconds.
        track (bool): Include the track count column.
        run_start (float): Run start (time.monotonic).
        run_end (float): Run end.
    """
    def row(name, frames, errors, fps_samples, lat, dets, kpts, faces, tracks):
        """Format one table row: counts, fps percentiles from per-second samples, latency percentiles and detection counts."""
        return (f'{name:>6} {frames:>7} {errors:>6} | {pct(fps_samples, 50):>7.1f} {pct(fps_samples, 95):>7.1f} {pct(fps_samples, 99):>7.1f} | '
                f'{pct(lat, 50):>8.1f} {pct(lat, 95):>8.1f} {pct(lat, 99):>8.1f} | {dets:>7} {kpts:>7} {faces:>7}' + (f' {tracks:>7}' if track else ''))
    print(f'{"stream":>6} {"frames":>7} {"errors":>6} | {"fps p50":>7} {"p95":>7} {"p99":>7} | {"ms p50":>8} {"p95":>8} {"p99":>8} | '
          f'{"dets":>7} {"kpts":>7} {"faces":>7}' + (f' {"tracks":>7}' if track else ''))
    for s in all_stats:
        print(row(s['stream'] + 1, s['frames'], s['errors'], per_second(s['done_at'], run_start, run_end), s['latencies'],
                  s['detections'], s['keypoints'], s['faces'], len(s['tracks'])))
    every = [t for s in all_stats for t in s['done_at']]
    lat = [ms for s in all_stats for ms in s['latencies']]
    dets, kpts, faces = (sum(s[k] for s in all_stats) for k in ('detections', 'keypoints', 'faces'))
    print(row('all', sum(s['frames'] for s in all_stats), sum(s['errors'] for s in all_stats),
              per_second(every, run_start, run_end), lat, dets, kpts, faces, 0))
    total = len(every)
    print(f'total: {total} frames in {wall:.1f}s = {total / wall:.1f} fps over {len(all_stats)} stream(s)')
    print(f'summary: frames={total} errors={sum(s["errors"] for s in all_stats)} streams={len(all_stats)} fps={total / wall:.1f} '
          f'fps_p50={pct(per_second(every, run_start, run_end), 50):.1f} detections={dets} keypoints={kpts} faces={faces} '
          f'latency_p50={pct(lat, 50):.1f} latency_p95={pct(lat, 95):.1f} latency_p99={pct(lat, 99):.1f}')


async def worker_async(args, ids: list[int], limit: int, geometry, shm_name: str | None, live_names, barrier) -> tuple[list[dict], int]:
    """Run the streams of one worker process.

    Attaches to the shared memory, optionally starts a Renderer that draws into the canvas, waits at the barrier so every worker starts together, then runs its streams concurrently.

    Args:
        args (argparse.Namespace): Parsed arguments.
        ids (list[int]): Global indexes of the streams this worker runs.
        limit (int): Maximum frames per stream.
        geometry: (width, height, rects) of the canvas, or None without --output.
        shm_name (str | None): Name of the canvas shared memory.
        live_names: Names of the live fps and live latency shared arrays.
        barrier: Start barrier shared with the parent.

    Returns:
        tuple[list[dict], int]: The stats of its streams and the number of frames not drawn.
    """
    live_shm = [shared_memory.SharedMemory(name=n) for n in live_names]
    live_fps, live_ms = (np.ndarray((args.streams,), np.float64, buffer=m.buf) for m in live_shm)
    canvas_shm = shared_memory.SharedMemory(name=shm_name) if shm_name else None
    all_stats = [new_stats(i, local) for local, i in enumerate(ids)]
    renderer = None
    if canvas_shm is not None:
        width, height, rects = geometry
        view = np.ndarray((height, width, 3), np.uint8, buffer=canvas_shm.buf)

        def place(local: int, tile: np.ndarray) -> None:
            """Copy a finished tile into this stream's rectangle of the canvas."""
            x, y, w, h = rects[ids[local]]
            view[y:y + h, x:x + w] = tile

        renderer = Renderer([(rects[i][2], rects[i][3]) for i in ids], place)
    stop = asyncio.Event()
    concurrency = args.concurrency or max(8, 4 * len(ids))
    async with AsyncAxVisionClient([e.strip() for e in args.endpoints.split(',') if e.strip()], concurrency=concurrency) as client:
        await asyncio.to_thread(barrier.wait)
        kpi = asyncio.create_task(kpi_loop(all_stats, live_fps, live_ms, stop))
        results = await asyncio.gather(*(run_stream(client, st, args, limit, args.fps, renderer) for st in all_stats))
        stop.set()
        await kpi
    if renderer is not None:
        await asyncio.to_thread(renderer.close)
    dropped = renderer.dropped if renderer is not None else 0
    for st in results:
        st.pop('recent')
    for st in all_stats:
        live_fps[st['stream']] = 0.0
    for m in live_shm + ([canvas_shm] if canvas_shm else []):
        release(m)
    return list(results), dropped


def worker_main(args, ids, limit, geometry, shm_name, live_names, barrier, results) -> None:
    """Entry point of a worker process; puts ('ok', result) or ('error', message) on `results`.

    On failure it also aborts the barrier so the other processes do not wait for it.
    """
    try:
        results.put(('ok', asyncio.run(worker_async(args, ids, limit, geometry, shm_name, live_names, barrier))))
    except BaseException as exc:
        try:
            barrier.abort()
        except Exception:
            pass
        results.put(('error', f'{type(exc).__name__}: {exc}'))


async def main_async(args) -> int:
    """Start the workers, show live progress, collect results and print the report.

    Args:
        args (argparse.Namespace): Parsed arguments.

    Returns:
        int: 0 if every stream completed frames without errors, otherwise 1.
    """
    limit = args.frames or (100 if Path(args.source).suffix.lower() in IMAGE_SUFFIXES else 10 ** 9)
    with make_adapter(args.source) as probe:
        args.source_fps = probe.target_fps
    fps = args.fps or args.source_fps
    workers = min(args.streams, args.workers or math.ceil(args.streams / STREAMS_PER_WORKER))
    ids = [list(range(w, args.streams, workers)) for w in range(workers)]
    ctx = multiprocessing.get_context('spawn')
    live_shm = [shared_memory.SharedMemory(create=True, size=args.streams * 8) for _ in range(2)]
    live_fps, live_ms = (np.ndarray((args.streams,), np.float64, buffer=m.buf) for m in live_shm)
    live_fps[:] = 0
    live_ms[:] = 0
    canvas = Canvas(args.output, args.streams, args.canvas, args.grid, fps, live_fps) if args.output else None
    geometry = (canvas.width, canvas.height, canvas.rects) if canvas else None
    barrier, results = ctx.Barrier(workers + 1), ctx.Queue()
    procs = [ctx.Process(target=worker_main, args=(args, ids[w], limit, geometry, canvas.shm.name if canvas else None,
                                                   [m.name for m in live_shm], barrier, results)) for w in range(workers)]
    for p in procs:
        p.start()
    try:
        await asyncio.to_thread(barrier.wait, 120)
    except Exception:
        pass
    start = time.monotonic()
    stop = asyncio.Event()
    tick = asyncio.create_task(canvas.run(stop)) if canvas else None

    async def live_print() -> None:
        """Print total fps and mean latency to stderr every LIVE_EVERY_S seconds."""
        last = start
        while not stop.is_set():
            await asyncio.sleep(0.5)
            now = time.monotonic()
            if now - last >= LIVE_EVERY_S:
                last = now
                busy = live_ms[live_ms > 0]
                print(f'[{now - start:5.0f}s] {float(live_fps.sum()):6.0f} fps  mean latency {float(busy.mean()) if busy.size else 0:.0f} ms',
                      file=sys.stderr)

    printer = asyncio.create_task(live_print())
    all_stats, dropped, failed = [], 0, []
    for _ in procs:
        while True:
            try:
                kind, payload = await asyncio.to_thread(results.get, True, 1.0)
                break
            except queue_mod.Empty:
                if not any(p.is_alive() for p in procs):
                    kind, payload = 'error', 'a worker process exited without a result'
                    break
        if kind == 'ok':
            all_stats += payload[0]
            dropped += payload[1]
        else:
            failed.append(payload)
    end = time.monotonic()
    stop.set()
    await printer
    if tick is not None:
        await tick
    for p in procs:
        p.join(timeout=10)
        if p.is_alive():
            p.terminate()
    all_stats.sort(key=lambda st: st['stream'])
    if failed:
        print('ERROR: ' + '; '.join(failed), file=sys.stderr)
    elif all_stats:
        report(all_stats, end - start, args.track, start, end)
        if canvas is not None:
            print(f'annotated canvas: {args.output} ({canvas.width}x{canvas.height}, {len(canvas.rects)} tiles, '
                  f'{canvas.frames_written} frames at {fps:g} fps; {dropped} frame(s) not drawn; {workers} client process(es))')
        else:
            print(f'{workers} client process(es)')
    if canvas is not None:
        canvas.close()
    for m in live_shm:
        release(m, unlink=True)
    return 0 if all_stats and not failed and all(st['frames'] and not st['errors'] for st in all_stats) else 1


def main(argv=None) -> int:
    """Validate the arguments and run the benchmark.

    Args:
        argv (list[str], optional): Arguments to parse. Defaults to sys.argv[1:].

    Returns:
        int: 0 on success, 1 on failed streams, 2 on invalid arguments or missing optional dependencies.
    """
    args = parse_args(argv)
    if not Path(args.source).is_file():
        print(f'ERROR: --source not found: {args.source}', file=sys.stderr)
        return 2
    if args.streams < 1 or args.inflight < 1 or args.concurrency < 0 or args.fps < 0 or args.workers < 0:
        print('ERROR: --streams and --inflight must be >= 1; --concurrency, --fps and --workers must not be negative', file=sys.stderr)
        return 2
    if args.output:
        try:
            import imageio_ffmpeg
        except ImportError:
            print('ERROR: --output needs imageio-ffmpeg (pip install imageio-ffmpeg, or re-run client/setup.sh)', file=sys.stderr)
            return 2
    try:
        parse_canvas_size(args.canvas)
        grid_layout(args.streams, args.grid)
    except ValueError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2
    if args.track:
        try:
            import ax_track
        except ImportError as exc:
            print(f'ERROR: --track needs the tracker dependencies ({exc}); install them with client/setup.sh --tracker', file=sys.stderr)
            return 2
    return asyncio.run(main_async(args))


if __name__ == '__main__':
    raise SystemExit(main())
