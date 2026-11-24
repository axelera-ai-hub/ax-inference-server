# Client Quick Start

This guide sets up the client side: the Python clients, the no-code pipeline-editor GUI (`app.py`), the helper and
the helper agent. It assumes the server side runs. Finish
[`../server/QUICKSTART.md`](../server/QUICKSTART.md) sections 1–3 first. The Docker container must run, and
`host_server.py` must answer on its health endpoint.

The GUI runs on the **bare host**. `host_server.py` runs **inside** the container. The GUI reaches it through the
container's bridge IP, never through `localhost`.

Set these variables in every shell you use:

```bash
WORKDIR=/path/to/your/ax_inference_server/checkout
SDK_DIR="$WORKDIR/.sdk/voyager-sdk"
CONTAINER=inference-server
```

Several steps need the address and the API key of `host_server.py`. Export them once per shell:

```bash
CONTAINER_IP=$(docker inspect "$CONTAINER" --format '{{.NetworkSettings.Networks.bridge.IPAddress}}')
export HOST_SERVER_URL="http://$CONTAINER_IP:8088"
export HOST_SERVER_API_KEY=$(docker exec "$CONTAINER" bash -c "grep '^DEPLOYMENT_API_KEY=' $WORKDIR/deployment/.env | cut -d= -f2-")
```

## 1. Set up the client

```bash
cd "$WORKDIR/client"
./setup.sh --agent
```

The script clones a pinned NiceGUI, builds the Vue Flow canvas bundle, creates the virtual environment
`client/ui/gui/.venv` and generates the gRPC client stubs. Every phase is idempotent, so you can re-run it.

`--agent` also installs Node and the Claude Code CLI, which the helper agent needs (section 5). Add more flags when
you need them:

| Flag | What it installs | When you need it |
| --- | --- | --- |
| `--debug` | Playwright, Chromium and Xvfb | You run the release suite (section 6). |
| `--tracker` | `roboflow/trackers` and `roboflow/supervision`, so `AxTrack` works | You use `--track` in `vision_demo.py`. |

The flags combine: `./setup.sh --agent --debug --tracker`.

## 2. Start the GUI

Stop every earlier GUI session first (section 3). Two GUIs cannot share a port. The second one then fails to start
while the first one still answers on that port.

```bash
cd "$WORKDIR/client"
./setup.sh --restart
```

The command stops a running `app.py` and starts a new one. It reads `HOST_SERVER_URL` and `HOST_SERVER_API_KEY`
from your shell, so export them first (see above). `app.py` finds the SDK itself through `host_server.py`. The GUI
listens on port 8080. Set `GUI_APP_PORT` before you run the command to use another port.

Check the result. The log must not show "address already in use":

```bash
curl -sf -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:8080/
tail -3 "$WORKDIR/client/ui/gui/.gui_live.log"
```

Open `http://<this host>:8080` in a browser. The GUI shows your client id. The helper agent needs it.

## 3. Stop the GUI

Never use bare `kill` or `pkill` on a shared host. Some hosts run an audit hook that ends your whole SSH session.
Resolve the PID first, then call `os.kill`:

```bash
PID=$(ps -eo pid,cmd | awk '/[a]pp\.py/ {print $1; exit}')
[ -n "$PID" ] && python3 -c "import os; os.kill($PID, 15)"
```

## 4. Prepare the server and run the examples

The GUI is one way to build pipelines. The helper is the other. Use `python -m helper` to provision models, write
configs and launch pipelines and vLLM servers from the command line. Then use `vision_demo.py` and `vllm_demo.py`
to send load to them. [`examples/README.md`](examples/README.md) lists every command.

```bash
cd "$WORKDIR/client/examples"
H="../ui/gui/.venv/bin/python3 -m helper"
$H health
$H devices
$H models provision yolox-m-coco-onnx
$H config isovision --pipelines 1 --model yolox-m-coco-onnx -o cfg/iso.yaml
$H up vision cfg/iso.yaml        # prints HOST:PORT of the pipeline
../ui/gui/.venv/bin/python3 vision_demo.py --endpoints HOST:PORT --source ../assets/test_images/dancing_frame_t15_480p.jpg
$H stop-all
```

## 5. Drive the GUI with an agent (MCP)

The helper agent is a Claude Code project. It builds, launches and benchmarks pipelines in the GUI through the
GUI's MCP server. It needs `--agent` from section 1, the running GUI from section 2 and an `ANTHROPIC_API_KEY`.
[`docs/helper/README.md`](docs/helper/README.md) describes the setup, the recommended flags and the example
prompts. In short:

```bash
source ~/.nvm/nvm.sh                          # puts claude on the PATH
cd "$WORKDIR/client/docs/helper/agent"
export GUI_APP_PORT=8080                      # the port of your GUI
export ANTHROPIC_API_KEY="sk-ant-..."
claude --model claude-haiku-5-5 --autocompact 500k --allowedTools "mcp__pipeline-editor-gui"
```

The agent follows the runbooks in
[`docs/helper/agent/runbook/index.md`](docs/helper/agent/runbook/index.md). Every MCP tool has a contract in
[`docs/gui/mcp-endpoints.md`](docs/gui/mcp-endpoints.md).

## 6. Run the release suite

The suite runs every `ui/gui/tests/test_release_*.py` acceptance test against the live GUI. It also runs the
`test_release_examples_*` tests, which drive `client/examples/` the way a user would.

Prepare these three things:

- Install the client with `./setup.sh --debug`. Without it the Playwright tests fail with
  `No module named 'playwright'`.
- Free the devices. The tests build and launch real pipelines and use the host's devices.
- Export `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` (see the top of this guide). The tests talk to
  `host_server.py` directly.

Run the suite:

```bash
cd "$WORKDIR/client"
./run_release_suite.sh http://127.0.0.1:8080     # use the port of your GUI
```

Do not use the GUI while the suite runs. The tests drive it, and a second user makes tests fail. The suite takes
about 45 minutes on an 8-device host.

Before each pipeline test the suite stops every pipeline on the host (`POST /api/v1/pipelines/cleanup-all`,
whoever started it). It also builds the models that the cascade tests need.

Each test prints `EXIT CODE for <test>: <rc>`. The last line reads `OVERALL RESULT: ALL_PASS` (exit code 0) or
`SOME_FAILED` (exit code 1). A test that misses a throughput target reports a warning ("PASS with N warning(s)")
and still passes.

The two cascade3 end-to-end tests also record an AxMonitor utilization trace. Run `AXMONITOR_TRACE=0
./run_release_suite.sh ...` to turn it off. If the trace cannot read utilization, it prints a `WARNING` and the
test still passes.
