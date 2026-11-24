# Benchmarking

## Overview

The Benchmarking tab measures a launched pipeline with live media sources.
Each source captures frames from an image, a video file or a webcam and sends them to an inference endpoint.
The tab plots frames per second, latency, errors, host load and AxMonitor device statistics.
A (V/L)LM chat panel on the same tab talks to vLLM servers launched from the Pipeline Editor.
Users open this tab after `Compile and Launch Pipeline` to find the throughput limit of a pipeline.

## Architecture

```mermaid
flowchart LR
    UI[app.py\nBenchmarking view] --> Bench[benchmark.py\nsource registry, plot, routes]
    Bench -->|MP_CONTEXT spawn| Worker[benchmark_worker.py\nrun_source_worker]
    Worker --> Adapter[SourceAdapter]
    Worker -->|AxVisionClient gRPC| Pipeline[Launched pipeline]
    Worker -->|JPEG ring buffer| Frames[benchmark_frames/source_id]
    Worker -->|metrics queue| Bench
    Frames --> Routes[/benchmark/thumbnail\n/benchmark/stream]
    Bench -->|queue-stats, monitor stats, media| Host[host_server.py]
    Chat[chat.py] --> VLLM[vLLM servers]
```

Each source runs in its own OS process.
`benchmark.py` starts the process through `MP_CONTEXT`, a `spawn` context, and keeps one entry per source id in `core.app.state.benchmark_sources`.
The worker owns one `SourceAdapter` (see [adapters.md](../client/adapters.md)).
With endpoints set, the worker sends frames through `AxVisionClient` and draws detections on the saved frames.
Without endpoints, the worker only captures and displays.
Frames never cross the process boundary.
The worker writes JPEG files to `benchmark_frames/<source_id>`, a ring buffer of 150 frames, and the GUI reads them by file name.
The worker publishes small metrics snapshots through a queue of size 1.
A GUI timer drains each queue every 0.5 s, and a second timer records one history sample every 2 s and redraws the plot.
At startup, `app.py` kills worker processes that a previous GUI instance left behind.

## Components

| Component | Description | Reference |
|---|---|---|
| `benchmark.py` | Owns the settings, the source registry, the live plot, AxMonitor polling and the preview routes. | [GUI reference](../reference/gui/index.md) |
| `benchmark_worker.py` | Provides `run_source_worker`, `make_adapter` and `MP_CONTEXT`. | [GUI reference](../reference/gui/index.md) |
| `chat.py` | Holds the chat sessions, the prompt library and the token estimate. | [GUI reference](../reference/gui/index.md) |
| `app.py` | Builds the Benchmarking view and the Advanced Settings drawer. | [GUI reference](../reference/gui/index.md) |

## Flow

1. The user opens `Add file` or `Add webcam`.
2. The tab opens the adapter once to validate the source. A failure shows a toast and adds no source.
3. The GUI assigns the id `src-<n>` and builds the source tile.
4. The GUI spawns the worker with the current endpoints, pipeline ids and stream settings.
5. The worker captures frames at the target FPS and submits them to the endpoints.
6. The worker writes frames to the ring buffer and publishes metrics.
7. The tile shows capture FPS, inference FPS, latency, detection count and error count.
8. The tile icon is red under backpressure, orange after inference errors and green otherwise.
9. Clicking the thumbnail opens the pinned stream, served from `GET /benchmark/stream/{source_id}`.
10. Removing a source stops the worker, waits 3 s, terminates it after 2 s more and deletes its frames.

### Adding sources

| Source | Behavior |
|---|---|
| File | A server-side folder browser starts at `client/assets/test_images`. It accepts `.jpg`, `.jpeg`, `.png`, `.bmp`, `.mp4`, `.avi`, `.mov` and `.mkv`. |
| Count | The `Count` field (1 to 50) adds that many identical sources, each with its own worker. |
| FPS | The `FPS` field sets the target rate. The limit is 2000 for images and 60 for videos. The default is 5. |
| Webcam | The dialog lists devices from `WebcamAdapterCV` and takes an FPS from 1 to 60. |
| Fetch media | The cloud button downloads the standard sample videos into the folder through the host server. |

The fetch button calls `POST /api/v1/benchmark-media/fetch` and polls `GET /api/v1/benchmark-media/status` every 0.75 s.
A 409 response means a fetch already runs, and the GUI treats it as started.
The endpoints are described in [host-server.md](../../../server/docs/host-server/host-server.md).
A tile `Target FPS` field retargets a running source.

### Live stats

The live stats plot offers these series.
Checkbox state survives page loads.

| Series | Default | Description |
|---|---|---|
| Aggregate FPS | on | Sums the inference FPS of all sources. A filter smooths it. |
| Per-source FPS | off | Plots the inference FPS of each source. |
| Per-source latency | on | Plots the latency of each source. |
| Per-source errors | off | Plots the error count of each source. |
| Aggregate errors | off | Plots the summed error count. |
| CPU utilization | off | Plots host CPU in percent. |
| Per-core CPU utilization | off | Adds one line per logical core. |
| Memory utilization | off | Plots host memory in percent. |
| AxMonitor aggregate core, MVM, sys-core, DDR | off | Plots the mean utilization across devices. |
| AxMonitor raw per-device | off | Plots the raw per-device statistics. |
| AxMonitor power sensor 0 and 1 | off | Plots the measured power of each sensor in watts. It sums the devices that report it. |

The Aggregate FPS filter is `ema` (default, alpha 0.3) or a Hampel filter (window 7, 3.0 sigmas).
The AxMonitor checkboxes stay disabled when the first poll of `GET /api/v1/monitor/stats` fails.
The GUI then stops polling for the life of the process.

### Advanced Settings drawer

A 16 px strip on the right edge of the Benchmarking tab opens the drawer on hover.
The drawer hides on the Pipeline Editor tab.
Settings marked "new sources" apply only to sources added afterwards.

| Setting | Default | Effect |
|---|---|---|
| Inference endpoint(s) | empty | Sets the `AxVisionClient` endpoints of new sources. Compile and launch fills it. |
| Pipeline ID(s) | empty | Selects the pipelines whose `GET /api/v1/pipelines/{id}/queue-stats` drives backoff. |
| History buffer | 1000 samples | Resizes the per-source and host histories. The range is 10 to 100000. |
| Thumbnail refresh interval | 7 s | Sets how often a tile thumbnail refreshes. The range is 1 to 60. |
| Stream FPS cap | 24 | Caps the stream polling rate and the worker render rate. The range is 1 to 60. |
| Disk save max width | 0 | Downscales saved frames. 0 keeps the native width. New sources. |
| Backpressure cap | 1000 | Limits in-flight requests. 0 removes the limit. New sources. |
| Client request timeout | 65 s | Sets the `AxVisionClient` gRPC deadline. New sources. |
| AIMD backoff | off | Lets a source slow its capture rate while the backend looks congested. New sources. |
| Stream resolution | `360p` | Serves the pinned stream at `native`, `720p`, `480p` or `360p`. |
| Stream quality | 80 | Sets the encode quality from 1 to 100. |
| Stream format | `webp` | Serves `webp` or `jpeg`. |
| Playback delay | 2 s | Holds playback behind capture time. The range is 0 to 10 s. |

The client request timeout must be at least the server-side `timeout` of the Input node.
A smaller value makes the client report `DEADLINE_EXCEEDED` first.
The stream FPS cap, the stream resolution, quality, format and the playback delay apply to open streams at once.
The stream resolution only resizes at serve time.
A stall longer than the playback delay empties the buffer and shows "rebuffering".

### AIMD backoff

The worker polls `queue-stats` every 2 s through a background thread.
A queue at 75 percent fill counts as congested.
A congested round multiplies the backoff multiplier by 1.5, up to 4.0.
A clean round divides it by 1.5, down to 1.0.
The worker multiplies the capture interval by the multiplier.
The tile shows the multiplier as a badge.

### Power limit

The drawer row `Set power limit` has a Device field, a Power (W) field and a Set button.
Set sends `POST /api/v1/devices/{id}/axdevice` with `power_limit_w`, then reads the value back.
The limit range is 0 to 500 W, and 0 turns the limit off.
The call has a 90 s timeout and works while pipelines run.
The row does not depend on the AxMonitor checkboxes.
The endpoint is described in the [host server reference](../../../server/docs/reference/host_server/index.md).

### (V/L)LM chat

The chat panel lists running vLLM servers from `GET /api/v1/vllm/status`.
Each server has its own session.
The panel sends text through `AsyncAxLlmClient` and text with images through `AsyncAxVlmClient`.
A message takes up to 8 images.
`Concurrent requests` (1 to 32) fans one message out across the running instances.
`Max new tokens` (default 128) sets `max_tokens`.
The prompt library stores prompts in `generated_configs/prompt_library.jsonl`.

## Configuration

| Setting | Default | Effect |
|---|---|---|
| `HOST_SERVER_URL` | empty | Locates `host_server.py` for media fetch, queue-stats, AxMonitor and power limits. |
| `HOST_SERVER_API_KEY` | empty | Sent as the `X-API-Key` header. |
| `GUI_APP_PORT` | `8080` | Sets the GUI port that serves the preview routes. |

## Constraints

- A worker captures frames without inference when the endpoint list is empty.
- A source needs a readable file or an available device. The GUI rejects it otherwise.
- Settings marked "new sources" do not change running workers.
- The preview routes return 404 for an unknown source or a source without frames.
- AxMonitor polling stops for the process lifetime after the first failed poll.

## Quick Example

Read the latest frame of a source through the preview route.

```bash
curl -o thumb.jpg http://localhost:8080/benchmark/thumbnail/src-1
```

## Related

- [pipeline-editor.md](pipeline-editor.md) launches the pipeline this tab measures.
- [mcp-endpoints.md](mcp-endpoints.md) lets an agent read `sources` metrics and frames.
- [adapters.md](../client/adapters.md) describes the `SourceAdapter` classes.
- [client.md](../client/client.md) describes `AxVisionClient`.
- [host-server.md](../../../server/docs/host-server/host-server.md) describes the endpoints this tab calls.

## Source files

- `client/ui/gui/benchmark.py`
- `client/ui/gui/benchmark_worker.py`
- `client/ui/gui/chat.py`
- `client/ui/gui/app.py`
