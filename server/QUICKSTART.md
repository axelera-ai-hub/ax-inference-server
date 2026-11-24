# Server Quick Start

This guide sets up the server side: the Docker container with the Voyager SDK, `host_server.py`, the model
artifacts and vLLM. The GUI and the Python clients are in [`../client/QUICKSTART.md`](../client/QUICKSTART.md).

`host_server.py` and the C++ server run **inside** the container. You reach the container's ports through its
bridge IP, never through `localhost`. The Python virtual environments exist only inside the container, so you run
their commands with `docker exec`.

Set these variables in every shell you use:

```bash
WORKDIR=/path/to/your/ax_inference_server/checkout
SDK_DIR="$WORKDIR/.sdk/voyager-sdk"
CONTAINER=inference-server
```

## 1. Set up the container and the SDK

```bash
cd "$WORKDIR/deployment"
./setup.sh --target docker \
  --sdk-repo-url https://github.com/axelera-ai-hub/voyager-sdk.git \
  --sdk-dest-dir "$SDK_DIR" \
  --sdk-ref v1.9.1 \
  --container-name "$CONTAINER" \
  --driver --monitor --vllm-axplugin
```

The first run builds the C++ server and installs packages. It takes about 25–30 minutes. Later runs are much
faster, because every phase is idempotent. You can re-run the command at any time.

| Flag | What it does |
| --- | --- |
| `--driver` | Installs or upgrades the Metis kernel driver on the host when the installed one is missing or older than the SDK requires. |
| `--monitor` | Installs and starts AxMonitor inside the container. |
| `--vllm-axplugin` | Creates `.venv-vllm` and installs the vLLM axplugin. Omit it if you only need gRPC pipelines. |
| `--force-rebuild-server` | Forces a clean C++ rebuild. You rarely need it. |

Each phase prints `PASS` or `SKIP`. `SKIP` lines for `compile_models` and `smoke_test` are normal.

`--driver` reads the installed version (`modinfo metis`) and compares it with the SDK's
`RELEASE_COMPATIBILITY_MATRIX.md`. A new driver only takes effect after you reload the module. Reboot, or stop
everything that uses the cards and run `sudo rmmod metis && sudo modprobe metis`.

If a download fails with "Name or service not known", the container cannot resolve a host that the bare host can.
`setup.sh` already pins working IPv4 addresses for `pypi.org` and `download.pytorch.org` when it creates the
container. Add `--force-recreate-container` to apply that fix to an older container. For any other host, add it to
`ADD_HOST_ARGS` in `deployment/setup.sh` (search for `PYPI_IP`).

## 2. Start an existing container

```bash
docker start "$CONTAINER"
```

After a host reboot, re-run the command from section 1 instead. The container restarts by itself, but its
device-cgroup major numbers stay frozen at the values from its creation. The kernel can assign new majors when the
driver reloads. With a stale major the container sees `/dev/metis-*` but cannot open it. You then see "Operation
not permitted" in `host_server.py` and "Device discovery unavailable (500)" in the GUI. `setup.sh` detects the
drift and tells you what to do. Usually you add `--force-recreate-container`.

### Restart a stuck container

Restart the container when a pipeline process holds a device after a crash. The GUI then shows "frame dropped:
client-side UNAVAILABLE", or a launch hangs. Re-run the command from section 1 with `--restart` added:

```bash
cd "$WORKDIR/deployment"
./setup.sh --target docker \
  --sdk-repo-url https://github.com/axelera-ai-hub/voyager-sdk.git \
  --sdk-dest-dir "$SDK_DIR" \
  --sdk-ref v1.9.1 \
  --container-name "$CONTAINER" \
  --driver --monitor --vllm-axplugin \
  --restart
```

The restart also stops `host_server.py`, and `setup.sh` relaunches it. It does not relaunch pipelines or vLLM
servers. Start them again (section 5 or the GUI). Every GUI that uses this container loses its pipelines, so check
for other users on a shared host first.

## 3. Check that `host_server.py` is up

Section 1 starts `host_server.py`. `docker start` does not. Check it:

```bash
docker exec "$CONTAINER" curl -sf -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:8088/api/v1/health
```

You expect `HTTP 200`. If the check fails, start the server:

```bash
docker exec "$CONTAINER" bash -c "
  cd $WORKDIR/deployment && set -a; source .env; set +a; source venv/bin/activate
  nohup uvicorn host_server:app --host \"\$BIND_HOST\" --port \"\$BIND_PORT\" > .host_server_live.log 2>&1 < /dev/null &
"
```

Do not start it when it already runs. A second instance fails to bind the port.

## 4. Deploy the model artifacts

vLLM needs model artifacts in the SDK's `build/` directory. You get them in two steps: download them, then deploy
them into the SDK.

The models are `qwen3-0.6b`, `qwen3_4b`, `qwen3_8b`, `llama3_1_8b`, `llama3_2_1b` and
`smolvlm2-256m-video-instruct`. Each one has a `server/models/<name>.link` file. A `.link` file is a bash script.
It downloads `<name>.tar.gz` from `https://media.axelera.ai` with `wget`, extracts it to `./<name>` and deletes the
archive. The download is public and needs no credentials.

**Download** the artifacts on the bare host. Run each `.link` from `server/models`, because it extracts into the
current directory. The host needs `wget` and `tar`:

```bash
cd "$WORKDIR/server/models"
bash qwen3-0.6b.link
bash smolvlm2-256m-video-instruct.link
```

**Deploy** them with `deploy_to_sdk.sh`. The script writes into `$SDK_DIR/build/`, which belongs to root inside the
container. Run it with `docker exec`:

```bash
docker exec "$CONTAINER" bash -c "
  cd $WORKDIR/server/models
  ./deploy_to_sdk.sh --sdk-dir $SDK_DIR --model qwen3-0.6b --model smolvlm2-256m-video-instruct
"
ls "$SDK_DIR/build/qwen3-0.6b/axscript" "$SDK_DIR/build/smolvlm2-256m-video-instruct/axscript"
```

Without this deploy step vLLM cannot find the models. Vision models need no `.link` file. The helper or the GUI
downloads them (see [`../client/examples/README.md`](../client/examples/README.md)).

## 5. Serve a model through vLLM

This section needs `--vllm-axplugin` from section 1 and the deployed artifacts from section 4.

A vLLM server claims a whole device while it runs. Give every server its own device and its own port. A host with
one device cannot run two vLLM servers at once.

### With the helper (recommended)

The helper is `python -m helper` from `client/examples/`. It picks a healthy device for you. It runs on the bare
host with the client environment from [`../client/QUICKSTART.md`](../client/QUICKSTART.md) section 1:

```bash
CONTAINER_IP=$(docker inspect "$CONTAINER" --format '{{.NetworkSettings.Networks.bridge.IPAddress}}')
export HOST_SERVER_URL="http://$CONTAINER_IP:8088"
export HOST_SERVER_API_KEY=$(docker exec "$CONTAINER" bash -c "grep '^DEPLOYMENT_API_KEY=' $WORKDIR/deployment/.env | cut -d= -f2-")

cd "$WORKDIR/client/examples"
H="../ui/gui/.venv/bin/python3 -m helper"
$H vllm up --artifact qwen3-0.6b --port 8000
$H vllm up --artifact smolvlm2-256m-video-instruct --port 8001
$H vllm status
```

Each `vllm up` prints the server URL when the server is ready, usually after 40 seconds. vLLM names the servers
with dashes, so `qwen3-0.6b` appears as `qwen3-0-6b` in `vllm status`. Use the name that `vllm status` prints in
`vllm down --name`.

Stop a server with `$H vllm down --name <name>`. Stop everything with `$H stop-all`.

### With `serve.sh`

Use `serve.sh` when you have no client environment. Set `DEVICE` to a device that exists on your host
(`ls /dev/metis-*`). The default `metis-0:23:0` does not exist on most hosts, and the server then fails with
"metis device not found":

```bash
docker exec -d "$CONTAINER" bash -c "
  cd $WORKDIR/server/vllm/axelera
  MODEL=$SDK_DIR/build/qwen3-0.6b/axscript PORT=8000 DEVICE=metis-0:3:0 \
  AXELERA_PYTHON=$WORKDIR/.venv-vllm/bin/python3 PYTHONPATH=$SDK_DIR \
    scripts/serve.sh > /tmp/vllm_serve_qwen3.log 2>&1
"
docker exec "$CONTAINER" curl -sf http://127.0.0.1:8000/health && echo UP
```

Start the vision-language model the same way. Use another `PORT` and another `DEVICE`:

```bash
docker exec -d "$CONTAINER" bash -c "
  cd $WORKDIR/server/vllm/axelera
  MODEL=$SDK_DIR/build/smolvlm2-256m-video-instruct/axscript PORT=8001 DEVICE=metis-0:4:0 \
  AXELERA_PYTHON=$WORKDIR/.venv-vllm/bin/python3 PYTHONPATH=$SDK_DIR \
    scripts/serve.sh > /tmp/vllm_serve_smolvlm2.log 2>&1
"
docker exec "$CONTAINER" curl -sf http://127.0.0.1:8001/health && echo UP
```

## 6. Send a request with curl

```bash
# qwen3-0.6b: plain completion
docker exec "$CONTAINER" curl -s http://127.0.0.1:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "'"$SDK_DIR"'/build/qwen3-0.6b/axscript", "prompt": "The capital of France is", "max_tokens": 16, "temperature": 0}'
```

```bash
# smolvlm2: chat completion with an image (the payload goes through a temp file)
IMG="$WORKDIR/client/assets/test_images/traffic_frame_480p.jpg"
MODEL_DIR="$SDK_DIR/build/smolvlm2-256m-video-instruct/axscript"
PAYLOAD=$(mktemp)
docker exec "$CONTAINER" python3 -c "
import base64, json
with open('$IMG', 'rb') as f: b64 = base64.b64encode(f.read()).decode()
json.dump({'model': '$MODEL_DIR', 'messages': [{'role': 'user', 'content': [
    {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
    {'type': 'text', 'text': 'Describe this image in one sentence.'}]}],
    'max_tokens': 32, 'temperature': 0}, open('$PAYLOAD', 'w'))
"
docker exec "$CONTAINER" curl -s http://127.0.0.1:8001/v1/chat/completions \
  -H "Content-Type: application/json" -d @"$PAYLOAD"
rm -f "$PAYLOAD"
```

A non-empty `content` in the smolvlm2 response shows that the image reached the model.

## 7. Stop things

Never use bare `kill` or `pkill` on a shared host. Some hosts run an audit hook that ends your whole SSH session.
Resolve the PID first, then call `os.kill`.

```bash
# host_server.py
docker exec "$CONTAINER" bash -c "
  PID=\$(ps -eo pid,cmd | awk '/uvicorn host_server:app/ && !/awk/ {print \$1; exit}')
  [ -n \"\$PID\" ] && python3 -c \"import os; os.kill(\$PID, 15)\"
"

# a vLLM server, by port (the command line contains "--port 8000" with a space)
docker exec "$CONTAINER" bash -c "
  PORT=8000
  PID=\$(ps -eo pid,cmd | awk -v p=\"--port \$PORT\" '/vllm.entrypoints.openai.api_server/ && index(\$0, p) && !/awk/ {print \$1; exit}')
  [ -n \"\$PID\" ] && python3 -c \"import os; os.kill(\$PID, 15)\"
"
```

Stop a vLLM server before you start another one on the same device. The device stays busy until the process exits.

## 8. Run the release suite

The suite runs `tests/test_release_host_server.py`. It checks the REST endpoints of `host_server.py`: health,
authentication, devices, models, vLLM status and a real device health check. It runs inside the container and
reads the API key from the deployment's `.env`. It never prints the key.

```bash
docker exec "$CONTAINER" bash -c "
  cd $WORKDIR/deployment && set -a; source .env; set +a
  cd $WORKDIR/server
  HOST_SERVER_URL=http://127.0.0.1:8088 HOST_SERVER_API_KEY=\$DEPLOYMENT_API_KEY ./run_release_suite.sh
"
```

The run takes about 30 seconds on an 8-device host. The last line reads `OVERALL RESULT: ALL_PASS` (exit code 0) or `SOME_FAILED` (exit
code 1). The suite can print a warning that only some devices are healthy. That warning is normal on a host with
faulty devices. It does not fail the suite.

The suite first calls `POST /api/v1/pipelines/cleanup-all`. That call stops every `axinferencenet_grpc` and vLLM
process on the host, including servers you started by hand. Check for other users on a shared host first. To keep
running processes, call the test directly with `--skip-cleanup`:

```bash
docker exec "$CONTAINER" bash -c "
  cd $WORKDIR/deployment && set -a; source .env; set +a
  cd $WORKDIR/server
  HOST_SERVER_API_KEY=\$DEPLOYMENT_API_KEY ../.venv-vllm/bin/python3 tests/test_release_host_server.py http://127.0.0.1:8088 --skip-cleanup
"
```

### Optional: device refresh, firmware reload and power limit

The test can also call `POST /api/v1/devices/{id}/axdevice`. This is opt-in, because a refresh and a firmware
reload reset the device and interrupt everything that uses it. Pass `--axdevice-device <N>` and pick a device that
is safe to reset. `run_release_suite.sh` does not pass this flag, so run the test directly:

```bash
docker exec "$CONTAINER" bash -c "
  cd $WORKDIR/deployment && set -a; source .env; set +a
  cd $WORKDIR/server
  HOST_SERVER_URL=http://127.0.0.1:8088 HOST_SERVER_API_KEY=\$DEPLOYMENT_API_KEY ../.venv-vllm/bin/python3 tests/test_release_host_server.py --axdevice-device 0 --axdevice-power 20
"
```

On device `<N>` the test refreshes the device and reloads the firmware. It sets the power limit to
`--axdevice-power` watts (default 20), reads it back with `GET /api/v1/devices/<N>/axdevice`, refreshes again and
checks that the limit survived, then restores the original limit. The value is the configured limit, not the live
power draw. A device without a `power-limit=` entry in `axdevice -v` gets a warning, and the test skips the power
steps. The step runs after `cleanup-all`, so the shared-host caution applies. The refresh needs a container
without AppArmor confinement, which `deployment/setup.sh` creates.
