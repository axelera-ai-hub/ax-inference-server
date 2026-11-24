"""Drive the host server (devices, models, pipelines, vLLM) from the command line.

Each subcommand maps to one step of the GUI workflow: check health, pick devices, provision models, write a config, compile, upload, launch, inspect and stop.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from . import config as cfgmod
from . import deploy, server
from .server import EXIT_FAIL, EXIT_OK, EXIT_USAGE, ServerError, UsageError, log


def cmd_health(args) -> int:
    """Check that the host server answers its health endpoint and log the reply."""
    log(f'server healthy: {server.check_health()}')
    return EXIT_OK


def cmd_devices(args) -> int:
    """List healthy devices, or print only the first healthy one.

    Prints a comma-separated list of device indexes (or a single index with --first) on stdout; per-device health goes to stderr.
    """
    if args.first:
        print(server.select_first_healthy(args.preferred))
        return EXIT_OK
    devices = server.healthy_devices(args.devices, args.num_devices)
    log(f'healthy devices: {devices}')
    print(','.join(str(d) for d in devices))
    return EXIT_OK


def cmd_stop_all(args) -> int:
    """Stop every pipeline and vLLM server on the host (the GUI "Force Stop All")."""
    log('stopping every pipeline and vLLM server on the host (the GUI\'s "Force Stop All")')
    body = server.stop_all()
    log(f'stopped pids={body.get("killed_pids")} vllm={body.get("killed_vllm_names")}')
    return EXIT_OK


def cmd_models(args) -> int:
    """List models, or provision prebuilt models on a device.

    For `provision`, each name is downloaded and compiled on --device (default: first healthy device), optionally patching its postprocess meta_key.
    """
    if args.action == 'list':
        for kind, names in server.list_models().items():
            print(f'{kind}:')
            for n in names:
                print(f'  {n}')
        return EXIT_OK
    device = args.device if args.device is not None else server.select_first_healthy()
    for name in args.names:
        server.provision_model(name, device, args.meta_key)
    return EXIT_OK


def cmd_power(args) -> int:
    """Read or set the power limit of one device.

    `get` prints the limit in watts, or `unset`. `set` prints the limit after the change.

    Raises:
        ServerError: If the axdevice call reports failure.
    """
    device = args.device if args.device is not None else server.select_first_healthy()
    if args.action == 'get':
        st = server.axdevice_status(device)
        log(st['device'])
        print('unset' if st['power_limit_w'] is None else st['power_limit_w'])
        return EXIT_OK
    res = server.set_power_limit(device, args.limit)
    log(f'device {device}: power limit {res["device_before"]!r} -> {res["device_after"]!r}')
    if not res['ok']:
        raise ServerError(f'axdevice failed: {[s["stderr"] or s["stdout"] for s in res["steps"]]}')
    print(res['power_limit_w_after'])
    return EXIT_OK


def cmd_pin(args) -> int:
    """Print the CPU list and NUMA node planned for each group of healthy devices."""
    topo = server.cpu_topology()
    log(f'numa_available={topo["numa_available"]} total_cpus={topo["total_cpus"]} nodes={topo["nodes"]}')
    devices = server.healthy_devices(args.devices, args.num_devices)
    groups = [devices[i:i + args.devices_per_pipeline] for i in range(0, len(devices), args.devices_per_pipeline)]
    for group, pin in zip(groups, server.pin_groups(groups, args.cores_per_device)):
        print(f'devices {",".join(map(str, group))}: taskset_cpus={pin["taskset_cpus"]} membind={pin["membind"]}')
    return EXIT_OK


def cmd_config(args) -> int:
    """Write one of the example pipeline configs (isovision, cascade, cascade3) as YAML to --output."""
    text = cfgmod.isovision(args) if args.example == 'isovision' else cfgmod.cascade(args, args.example == 'cascade3')
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(text)
    log(f'wrote {args.output}')
    return EXIT_OK


def cmd_compile(args) -> int:
    """Compile a config YAML into pipeline specs and print the output directory."""
    print(deploy.compile_config(args.config, args.output_dir))
    return EXIT_OK


def cmd_upload(args) -> int:
    """Upload the compiled specs in a directory to the server."""
    deploy.upload(args.directory)
    return EXIT_OK


def cmd_launch(args) -> int:
    """Launch the uploaded pipelines and print one host:port endpoint per line."""
    for ep in deploy.launch(args.directory):
        print(ep)
    return EXIT_OK


def cmd_up(args) -> int:
    """Compile, upload and launch a config in one step, printing one endpoint per line."""
    out = deploy.compile_config(args.config, args.output_dir)
    deploy.upload(str(out))
    for ep in deploy.launch(str(out)):
        print(ep)
    return EXIT_OK


def cmd_down(args) -> int:
    """Stop pipelines named by a compiled directory or by --ids."""
    deploy.down(deploy.pipeline_ids(args.directory, args.ids))
    return EXIT_OK


def cmd_status(args) -> int:
    """Print queue stats for pipelines.

    Returns:
        int: EXIT_OK if every pipeline reported healthy stats, otherwise EXIT_FAIL.
    """
    return EXIT_OK if deploy.status(deploy.pipeline_ids(args.directory, args.ids), args.wait) else EXIT_FAIL


def cmd_media(args) -> int:
    """Fetch the sample videos into the server's client/assets/test_images/.

    Raises:
        ServerError: If any file failed to download.
    """
    results = server.fetch_media()
    for r in results:
        print(f'{r["file"]}: {r["status"]} {r["detail"]}'.rstrip())
    failed = [r['file'] for r in results if r['status'] == 'error']
    if failed:
        raise ServerError(f'media fetch failed for {failed}')
    log('media is in client/assets/test_images/ of the server tree')
    return EXIT_OK


MAX_IMAGES_VLM = 8


def cmd_vllm(args) -> int:
    """Start, stop or list vLLM servers.

    `up` needs --artifact and prints the base URL of the new server. `down` needs --name. `status` prints one line per instance.

    Returns:
        int: EXIT_OK for `up` and `down`. For `status`, EXIT_OK only if at least one instance exists and all are running, else EXIT_FAIL.

    Raises:
        UsageError: If `up` has no --artifact or `down` has no --name.
    """
    host = urlparse(server.require_env()[0]).hostname
    if args.action == 'up':
        if not args.artifact:
            raise UsageError('vllm up needs --artifact NAME (see `models list`)')
        name = args.name or re.sub(r'[^A-Za-z0-9_-]', '-', args.artifact)
        device = args.device if args.device is not None else server.select_first_healthy()
        log(f'starting vLLM {name} ({args.artifact}) on device {device}, port {args.port}; takes 1-2 minutes')
        res = server.vllm_up(name, args.artifact, args.port, device, args.thinking, args.temperature)
        log(f'{name}: pid {res["pid"]} context_length {res.get("context_length")}'
            + (f', up to {MAX_IMAGES_VLM} images per prompt' if 'vlm' in args.artifact else ''))
        print(f'http://{host}:{res["port"]}')
    elif args.action == 'down':
        if not args.name:
            raise UsageError('vllm down needs --name')
        log(f'{args.name}: ' + ('stopped' if server.vllm_down(args.name) else 'not running (not started by this server)'))
    else:
        instances = server.vllm_status()
        for i in instances:
            images = f' max_images={MAX_IMAGES_VLM}' if 'vlm' in i['name'] else ''
            print(f'{i["name"]}: http://{host}:{i["port"]} running={i["running"]} pid={i["pid"]} '
                  f'context_length={i["context_length"]}{images}')
        return EXIT_OK if instances and all(i['running'] for i in instances) else EXIT_FAIL
    return EXIT_OK


def _tuning(p) -> None:
    """Add the options shared by every `config` example (imdecode tuning, --pin, --devices, --output) to a parser."""
    p.add_argument('--imdecode-threads', type=int, help='default 4')
    p.add_argument('--imdecode-queue-depth', type=int, help='default 32')
    p.add_argument('--imdecode-queue-timeout-ms', type=int, help='default 20000')
    p.add_argument('--pin', action='store_true', help="pin each pipeline's CPUs (taskset/membind) from the server's NUMA plan")
    p.add_argument('--devices', default='auto', help="'auto' (healthy devices, default) or '0,1,2'")
    p.add_argument('-o', '--output', required=True, help='config YAML to write')


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with one subparser per subcommand."""
    parser = argparse.ArgumentParser(prog='python -m helper', description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('health', help='GET /api/v1/health')
    p.set_defaults(func=cmd_health)

    p = sub.add_parser('devices', help='health-check devices (POST /api/v1/devices/health); prints the healthy indexes')
    p.add_argument('--devices', default='auto', help="'auto' (default), '0' or '0,1,2'")
    p.add_argument('--num-devices', type=int, default=1, help="with --devices auto: how many healthy devices")
    p.add_argument('--first', action='store_true', help='print only the index of the first healthy device')
    p.add_argument('--preferred', type=int, default=0, help='with --first: the device tried first (default 0)')
    p.set_defaults(func=cmd_devices)

    p = sub.add_parser('stop-all', help="the GUI's Force Stop All: stop every pipeline and vLLM server on the host")
    p.set_defaults(func=cmd_stop_all)

    p = sub.add_parser('models', help='list models, or provision prebuilt models (download + compile)')
    p.add_argument('action', choices=['list', 'provision'])
    p.add_argument('names', nargs='*', help='provision: model names, e.g. yolox-m-coco-onnx')
    p.add_argument('--device', type=int, help='provision: device to compile on (default: first healthy)')
    p.add_argument('--meta-key', help="provision: postprocess meta_key to patch into the .axnet (e.g. 'detections')")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser('power', help='read or set a device power limit (axdevice, through host_server.py)')
    p.add_argument('action', choices=['get', 'set'])
    p.add_argument('--device', type=int, help='default: first healthy device')
    p.add_argument('--limit', help="set: watts, or 'off'")
    p.set_defaults(func=cmd_power)

    p = sub.add_parser('pin', help="show the CPU/NUMA pinning host_server.py plans for healthy devices")
    p.add_argument('--devices', default='auto')
    p.add_argument('--num-devices', type=int, default=4)
    p.add_argument('--devices-per-pipeline', type=int, default=1)
    p.add_argument('--cores-per-device', type=int, default=4)
    p.set_defaults(func=cmd_pin)

    p = sub.add_parser('config', help="write one of the GUI's example pipelines as a config YAML")
    ex = p.add_subparsers(dest='example', required=True)
    e = ex.add_parser('isovision', help='N independent single-detector pipelines')
    _tuning(e)
    e.add_argument('--pipelines', type=int, default=1)
    e.add_argument('--devices-per-pipeline', type=int, default=1)
    e.add_argument('--model', default='yolox-m-coco-onnx')
    e.add_argument('--meta-key', help='meta_key_override for the model')
    e.add_argument('--cores', type=int, default=4, help='AIPU cores per device (1-4)')
    e.add_argument('--port', type=int, default=50060, help='first pipeline port')
    for name, doc in (('cascade', 'detector -> filter -> secondary per crop'),
                      ('cascade3', 'detector -> filter -> secondary -> tertiary when the keypoint condition holds')):
        e = ex.add_parser(name, help=doc)
        _tuning(e)
        e.add_argument('--detector', default='yolox-m-coco-onnx')
        e.add_argument('--secondary', default='yolo26npose-coco-onnx')
        e.add_argument('--detector-meta-key', default='detections')
        e.add_argument('--secondary-meta-key', default='keypoint_detections')
        e.add_argument('--secondary-meta-key-override', action='store_true', help='patch the secondary model to --secondary-meta-key')
        e.add_argument('--classes', default='0', help="filter: class indices to crop ('' = all), default 0 (person)")
        e.add_argument('--detector-cores', type=int)
        e.add_argument('--secondary-cores', type=int)
        e.add_argument('--tertiary-cores', type=int)
        e.add_argument('--port', type=int, default=50063 if name == 'cascade' else 50064)
        e.add_argument('--pipeline-id', default='cascade-demo' if name == 'cascade' else 'cascade3-demo')
        if name == 'cascade3':
            e.add_argument('--tertiary', default='retinaface-mobilenet0.25-widerface-onnx')
            e.add_argument('--tertiary-meta-key', default='face_detections')
            e.add_argument('--keypoint-indices', default='0,1,2', help='condition: keypoints that must be visible')
            e.add_argument('--keypoint-threshold', type=float, default=0.5, help='condition: minimum keypoint confidence')
    p.set_defaults(func=cmd_config)

    p = sub.add_parser('compile', help='validate + compile a config YAML into pipeline specs (patches meta_key_overrides first)')
    p.add_argument('config')
    p.add_argument('--output-dir', help='default: compiled/<pipeline id>')
    p.set_defaults(func=cmd_compile)

    p = sub.add_parser('upload', help='upload the compiled specs to the server')
    p.add_argument('directory', help='output of `compile`')
    p.set_defaults(func=cmd_upload)

    p = sub.add_parser('launch', help='launch the uploaded pipelines; prints host:port per pipeline')
    p.add_argument('directory')
    p.set_defaults(func=cmd_launch)

    p = sub.add_parser('up', help='compile + upload + launch a config in one step')
    p.add_argument('kind', choices=['vision'])
    p.add_argument('config')
    p.add_argument('--output-dir')
    p.set_defaults(func=cmd_up)

    for name, doc in (('down', 'stop pipelines'), ('status', 'queue stats of pipelines (exit 1 if none or unhealthy)')):
        p = sub.add_parser(name, help=doc)
        p.add_argument('directory', nargs='?', help='compiled directory')
        p.add_argument('--ids', help='pipeline ids a,b instead of a directory')
        if name == 'status':
            p.add_argument('--wait', type=float, default=0.0, help='seconds to wait for each pipeline\'s first stats line')
        p.set_defaults(func=cmd_down if name == 'down' else cmd_status)

    p = sub.add_parser('media', help='fetch the sample videos (traffic/intersection/dancing, 480p-1080p) into client/assets/test_images/')
    p.set_defaults(func=cmd_media)

    p = sub.add_parser('vllm', help='start/stop/list vLLM (LLM or VLM) servers')
    p.add_argument('action', choices=['up', 'down', 'status'])
    p.add_argument('--artifact', help="up: compiled artifact, e.g. qwen3-0.6b or smolvlm2-256m-video-instruct")
    p.add_argument('--name', help='instance name (default: the artifact name)')
    p.add_argument('--port', type=int, default=8000)
    p.add_argument('--device', type=int, help='up: default first healthy device (a device running vLLM is not healthy)')
    p.add_argument('--thinking', action='store_true', help='up: enable chat-template thinking mode')
    p.add_argument('--temperature', type=float, default=0.0)
    p.set_defaults(func=cmd_vllm)
    return parser


def main(argv=None) -> int:
    """Run the CLI.

    Args:
        argv (list[str], optional): Arguments to parse. Defaults to sys.argv[1:].

    Returns:
        int: EXIT_OK on success, EXIT_FAIL on a server error, EXIT_USAGE on a usage error.
    """
    args = build_parser().parse_args(argv)
    try:
        if args.command == 'models' and args.action == 'provision' and not args.names:
            raise UsageError('models provision needs at least one model name')
        if args.command == 'power' and args.action == 'set' and not args.limit:
            raise UsageError("power set needs --limit WATTS|off")
        return args.func(args)
    except UsageError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return EXIT_USAGE
    except ServerError as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return EXIT_FAIL


if __name__ == '__main__':
    raise SystemExit(main())
