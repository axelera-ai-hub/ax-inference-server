# Client examples

Three runnable examples of the Axelera inference client:

| File | What it does |
| --- | --- |
| `vision_demo.py` | Several video or image streams through one `AsyncAxVisionClient`, paced at a target fps, with fps and latency P50/P95/P99 per stream and in total, one annotated canvas video and optional tracking |
| `vllm_demo.py` | One-shot prompt to a vLLM LLM (`qwen3-0.6b`) or VLM (`smolvlm2-256m-video-instruct`), with time to first token and tokens/s |
| `helper/` | `python -m helper <command>`: the preparation steps (models, configs, launch, vLLM) through `host_server.py`'s REST API |

The scripts assume the server side is ready: the devices are healthy, the models are provisioned, and a pipeline or
vLLM server is running at the address you pass. You can prepare that in the no-code GUI or with the helper (see
[Preparing the server](#preparing-the-server)). The scripts do not import the helper and the helper does not run the
scripts.

All commands use the client Python environment from [../QUICKSTART.md](../QUICKSTART.md) and run from `client/examples/`:

```bash
cd client/examples
PY=../ui/gui/.venv/bin/python3
```

## Vision: `vision_demo.py`

```bash
# 1 stream, one image, 100 frames
$PY vision_demo.py --endpoints HOST:50060 --source ../assets/test_images/dancing_frame_t15_480p.jpg

# 4 streams of a video on one annotated canvas video (2x2 grid, 480p)
$PY vision_demo.py --endpoints HOST:50060 --streams 4 --source ../assets/test_images/intersection_480p.mp4 \
    --frames 300 --output out.mp4

# 12 streams at 59 fps each over 4 pipelines, 4x3 grid
$PY vision_demo.py --endpoints HOST:50060,HOST:50061,HOST:50062,HOST:50063 --streams 12 --fps 59 \
    --source ../assets/test_images/intersection_480p.mp4 --frames 3000 --grid 4x3 --output canvas.mp4

# 8 streams spread over two pipelines (two endpoints), more requests in flight
$PY vision_demo.py --endpoints HOST:50060,HOST:50061 --streams 8 \
    --source ../assets/test_images/intersection_480p.mp4 --frames 300 --concurrency 16

# 44 streams at 60 fps (2640 fps) over 15 pipelines, 11x4 grid, 6 client processes, pinned to their own CPUs
taskset -c 24-47,108-131 $PY vision_demo.py --endpoints $EP15 --streams 44 --fps 60 --workers 6 \
    --source ../assets/test_images/intersection_480p.mp4 --frames 1800 --grid 11x4 --canvas 1080p --output canvas44.mp4

# tracking: ids drawn on the boxes (needs ../setup.sh --tracker)
$PY vision_demo.py --endpoints HOST:50060 --streams 2 --source ../assets/test_images/intersection_480p.mp4 \
    --track --output tracked.mp4
```

| Option | Meaning |
| --- | --- |
| `--endpoints` | `host:port[,host:port...]` of running vision pipelines; requests are spread over all of them |
| `--streams` | concurrent streams, all playing `--source` (default 1) |
| `--source` | image or video file |
| `--frames` | frames per stream (default: a video once through, an image 100) |
| `--fps` | rate each stream is fed at, also the canvas video's rate (default: the source's own rate) |
| `--workers` | client processes the streams are split over, each with its own client and GIL (default: one per 11 streams). One process tops out around 600 fps, so large stream counts need several |
| `--inflight` | frames each stream keeps submitted to the server (default 2). Inference queueing, not rendering: at saturation more in flight only adds latency (about streams x inflight / total fps) |
| `--concurrency` | the client's total in-flight request limit (default 4 per stream, at least 8) |
| `--output` | one annotated H.264 mp4 with every stream as a tile; encoded while running with the ffmpeg binary of the `imageio-ffmpeg` package (installed by `../setup.sh`) |
| `--canvas` | canvas size `360p`, `480p` (default), `720p`, `1080p`, `1440p`, `2160p` or `WxH` |
| `--grid` | tile grid `COLSxROWS` with room for all streams (default: the smallest near-square grid, 12 streams = 4x3) |
| `--track` | track detections across frames with `AxTrack` and draw track ids |

The canvas shows each stream's rolling fps and latency on its tile (top-left), the aggregate fps bottom-left and the
Axelera logo bottom-right. Inference has priority: tiles are drawn by low-priority threads from the newest frames, so on
a busy client some frames are detected and counted but never drawn. The video runs at `--fps` in real time and repeats
a stream's latest tile until a newer one is ready. In the table, fps is frames completed per second of the run.

The result table has one row per stream and an `all` row: frames, errors, fps and latency P50/P95/P99, and the counts of
detections (`dets`), detections with pose keypoints (`kpts`) and detections with a face box (`faces`; cascade pipelines
fill the last two). The last line is a stable `summary:` line for scripts, for example
`summary: frames=2400 errors=0 streams=4 fps=314.5 fps_p50=348.0 detections=52660 keypoints=0 faces=0 latency_p50=43.4 ...`
(`fps` is the whole run, `fps_p50` the steady per-second rate without the ramp-up).

Exit code 0 = ok, 1 = inference errors or no frames, 2 = usage or environment error (for example a missing source or
missing tracker dependencies).

Each stream is a source adapter (`client/adapters`) feeding `await client.infer(frame)`. To use your own source (a
camera, a stream, a folder), write an adapter that returns `Frame` objects from `read_frame()` (see
`adapters/base.py` and `adapters/video_file_cv.py`) and use it in `make_adapter()`.

## LLM and VLM: `vllm_demo.py`

```bash
# LLM, one prompt; --loop 5 repeats it and reports the averages
$PY vllm_demo.py llm --url http://HOST:8000 --prompt "Explain in two sentences what an NPU is." --loop 5

# VLM, one or more images (comma-separated, up to 8, best when they have the same size)
$PY vllm_demo.py vlm --url http://HOST:8001 --images ../assets/test_images/dancing_frame_t5_480p.jpg,../assets/test_images/dancing_frame_t15_480p.jpg \
    --prompt "Describe the images."
```

It prints the answer, then per request the time to first token, tokens and tokens/s, then the averages. Other options:
`--max-new-tokens`, `--thinking`, and for the VLM `--resize N` (off by default).
Exit code 0 = ok, 1 = request failed, 2 = usage error.

## Preparing the server

`HOST_SERVER_URL` is the `host_server.py` address (for example `http://HOST:8088`) and `HOST_SERVER_API_KEY` its API
key (`DEPLOYMENT_API_KEY` in `deployment/.env`). Every command exits 0 on success, 1 on failure, 2 on a usage or
environment error. Progress goes to stderr; results (device lists, endpoints, URLs) to stdout.

```bash
export HOST_SERVER_URL=http://HOST:8088 HOST_SERVER_API_KEY=...
H="$PY -m helper"

$H health                                   # is the server up
$H devices                                  # healthy devices (--devices 0,1 | --num-devices N | --first)
$H stop-all                                 # stop every pipeline and vLLM server on the host
$H power get                                # power limit of a device (--device N)
$H power set --limit 100                    # watts or 'off' (devices without limit control report an error)
$H pin --num-devices 4                      # CPU pinning the server plans per device (taskset_cpus / membind)

$H models list                              # prebuilt models, built models, vLLM artifacts
$H models provision yolox-m-coco-onnx       # download + compile for a healthy device (--device N, --meta-key K)
$H media                                    # sample videos into client/assets/test_images/ (traffic, intersection, dancing)
```

Vision pipelines are described by a config YAML. Write one of the GUI's three example pipelines, or export a YAML from
the GUI, then compile, upload and launch it:

```bash
# isovision: independent single-detector pipelines (here 2, each on its own device, pinned)
$H config isovision --pipelines 2 --devices-per-pipeline 1 --model yolox-m-coco-onnx --pin -o cfg/iso.yaml
# two-stage cascade: detector -> filter (person) -> pose per crop
$H config cascade --detector yolox-m-coco-onnx --secondary yolo26npose-coco-onnx --classes 0 -o cfg/cascade.yaml
# three-stage conditional cascade: ... -> face detection when the nose and eye keypoints are visible
$H config cascade3 --keypoint-indices 0,1,2 --keypoint-threshold 0.5 -o cfg/cascade3.yaml

$H compile cfg/iso.yaml                     # validate + compile into compiled/<id>/ (applies meta_key_override)
$H upload compiled/iso-detect_plus1         # send the specs to the server
$H launch compiled/iso-detect_plus1         # start them; prints HOST:PORT per pipeline
$H up vision cfg/iso.yaml                   # compile + upload + launch in one step
$H status compiled/iso-detect_plus1         # queue stats (--wait SECONDS for the first stats; exit 1 if unhealthy)
$H down compiled/iso-detect_plus1           # stop them (or: down --ids iso-detect,iso-detect-0)
```

`config` takes counts, models, devices, cores (`--cores`, `--detector-cores`, ...), `--pin`, the filter classes
(`--classes`) and the imdecode settings; run `$H config isovision -h` for the list. Models used by a config must be
provisioned first. The cascade configs need the models `yolox-m-coco-onnx`, `yolo26npose-coco-onnx` and (cascade3)
`retinaface-mobilenet0.25-widerface-onnx`.

vLLM servers (they need a device each; a device running vLLM is no longer healthy, so the next `up` picks another):

```bash
$H vllm up --artifact qwen3-0.6b --port 8000                          # prints http://HOST:8000
$H vllm up --artifact smolvlm2-256m-video-instruct --port 8001
$H vllm status                                                        # running, context length, image limit for VLMs
$H vllm down --name smolvlm2-256m-video-instruct
```

`vllm up` checks the devices and starts the server on the first healthy one, so you need no `--device`. vLLM serves
every model under a dashed name. The artifact `qwen3-0.6b` runs as `qwen3-0-6b`. `vllm status` prints that name,
and `vllm down --name` needs it. `vllm down --name qwen3-0.6b` reports "not running".
