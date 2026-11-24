"""Generate example pipeline config YAML (the same pipelines as the GUI examples).

Exposes `isovision` (N independent single-detector pipelines) and `cascade` (detector, filter, per-crop secondary, optional tertiary).

Note:
    Both generators query the server for healthy devices, so they need HOST_SERVER_URL and HOST_SERVER_API_KEY.
"""


from __future__ import annotations

import yaml

from . import server
from .server import UsageError

CORES_PER_DEVICE = 4
GLOBAL = {'use_axinference_net_opencl': '--enable-opencl', 'use_simd_decode': 1, 'restart_interval': 0}
DEFAULT_IMDECODE = {'imdecode_threads': 4, 'imdecode_queue_depth': 32, 'imdecode_queue_timeout_ms': 20000}


def axnet_path(model: str) -> str:
    """Return the ${SDK_ROOT}-relative path of the compiled .axnet for a model name."""
    return f'${{SDK_ROOT}}/build/{model}/{model}.axnet'


def _axnet_config(device_cores: list[tuple[int, int]]) -> str:
    """Format (device, cores) pairs as an axnet_config string, one `net-<i>;devices:<device>-<cores>` entry per pair joined by `;`."""
    return ';'.join(f'net-{i};devices:{d}-{c}' for i, (d, c) in enumerate(device_cores))


def _int_list(text: str) -> list[int]:
    """Parse a comma-separated string into a list of ints, skipping blank items."""
    return [int(x) for x in text.split(',') if x.strip()]


def _resolve_devices(spec: str, needed: int) -> list[int]:
    """Select healthy devices for a config.

    Args:
        spec (str): 'auto' or a comma-separated list of device indexes.
        needed (int): Number of devices required.

    Returns:
        list[int]: The selected device indexes.

    Raises:
        UsageError: If fewer than `needed` devices are returned.
    """
    devices = server.healthy_devices(spec, needed)
    if len(devices) < needed:
        raise UsageError(f'need {needed} device(s), got {devices}')
    return devices


def _pipeline_tuning(args) -> dict:
    """Return the imdecode settings from args, falling back to DEFAULT_IMDECODE for options left as None."""
    out = {}
    for field in DEFAULT_IMDECODE:
        value = getattr(args, field)
        out[field] = DEFAULT_IMDECODE[field] if value is None else value
    return out


def _document(nets: dict, pipelines: list[dict], predicates: dict | None = None) -> str:
    """Serialise nets, pipelines and optional predicates, together with the global section, to a YAML string."""
    raw = {'global': dict(GLOBAL), 'nets': nets}
    if predicates:
        raw['predicates'] = predicates
    raw['pipelines'] = pipelines
    return yaml.safe_dump(raw, sort_keys=False, default_flow_style=False)


def isovision(args) -> str:
    """Build the config for N independent single-detector pipelines.

    Each pipeline gets its own net on `--devices-per-pipeline` devices and a gRPC port of `--port` plus its index. Pipeline ids are `iso-detect`, `iso-detect-0`, `iso-detect-1`, and so on.

    Args:
        args (argparse.Namespace): Parsed `config isovision` options.

    Returns:
        str: The config as YAML.

    Raises:
        UsageError: If not enough devices are available.
    """
    count, per = args.pipelines, args.devices_per_pipeline
    devices = _resolve_devices(args.devices, count * per)
    groups = [devices[i * per:(i + 1) * per] for i in range(count)]
    if len(devices) < count * per:
        raise UsageError(f'{count} pipelines x {per} devices needs {count * per} devices, got {devices}')
    pins = server.pin_groups(groups, args.cores) if args.pin else [None] * count
    nets, pipelines = {}, []
    for i, group in enumerate(groups):
        net = f'net-{i + 1}'
        nets[net] = {'axnet': axnet_path(args.model),
                     'axnet_config': _axnet_config([(d, args.cores) for d in group])}
        if args.meta_key:
            nets[net]['meta_key_override'] = args.meta_key
        entry = {'id': 'iso-detect' if i == 0 else f'iso-detect-{i - 1}', 'interface': 'grpc', 'port': args.port + i,
                 'im_decode_output_format': 'I420', 'timeout': 60,
                 'graph': {'entry': net, 'nodes': [{'id': net, 'type': 'net', 'net': net, 'next': 'sink'},
                                                   {'id': 'sink', 'type': 'sink'}]}}
        if pins[i]:
            entry['taskset_cpus'] = pins[i]['taskset_cpus']
            if pins[i]['membind'] is not None:
                entry['membind'] = pins[i]['membind']
        entry.update(_pipeline_tuning(args))
        pipelines.append(entry)
    return _document(nets, pipelines)


def cascade(args, conditional: bool) -> str:
    """Build the config for a detector, filter and per-crop secondary pipeline.

    Each detected region of interest is processed in a loop (roi_iter, secondary, roi_collect, loop_guard, at most 50 iterations). With `conditional` set, a tertiary net runs on a crop only when the secondary's keypoint confidence condition holds.
    With `--devices auto` it prefers two devices and falls back to one; on a single device the cores are split between the stages.

    Args:
        args (argparse.Namespace): Parsed `config cascade` or `config cascade3` options.
        conditional (bool): True to add the tertiary stage behind a keypoint condition.

    Returns:
        str: The config as YAML.

    Raises:
        UsageError: If the stages claim more than CORES_PER_DEVICE cores on a device, or no device is available.
    """
    stages = 3 if conditional else 2
    if args.devices == 'auto':
        try:
            devices = _resolve_devices('auto', 2)
        except server.ServerError:
            devices = _resolve_devices('auto', 1)
    else:
        devices = _resolve_devices(args.devices, 1)
    first = devices[0]
    second = devices[1] if len(devices) > 1 else first
    single = second == first
    det_cores = args.detector_cores or (2 if single else CORES_PER_DEVICE)
    sec_cores = args.secondary_cores or ((1 if conditional else 2) if single else (2 if conditional else CORES_PER_DEVICE))
    ter_cores = args.tertiary_cores or (1 if single else 2)
    claimed: dict[int, int] = {}
    stage_cores = [(first, det_cores), (second, sec_cores)] + ([(second, ter_cores)] if conditional else [])
    for dev, cores in stage_cores:
        claimed[dev] = claimed.get(dev, 0) + cores
    over = {d: c for d, c in claimed.items() if c > CORES_PER_DEVICE}
    if over:
        raise UsageError(f'cores over-subscribed (max {CORES_PER_DEVICE} per device): {over}; set --detector-cores/--secondary-cores/--tertiary-cores')

    det_key = args.detector_meta_key
    sec_key = args.secondary_meta_key
    nets = {'det': {'axnet': axnet_path(args.detector), 'axnet_config': _axnet_config([stage_cores[0]]), 'meta_key_override': det_key},
            'secondary': {'axnet': axnet_path(args.secondary), 'axnet_config': _axnet_config([stage_cores[1]])}}
    nodes = [{'id': 'detect', 'type': 'net', 'net': 'det', 'next': 'filter'}]
    filter_node = {'id': 'filter', 'type': 'filter', 'meta_key': det_key, 'next': 'roi_iter'}
    if args.classes:
        filter_node['classes'] = _int_list(args.classes)
    nodes.append(filter_node)
    nodes.append({'id': 'roi_iter', 'type': 'roi_iter', 'meta_key': det_key, 'next': 'secondary', 'skip_to': 'out'})
    predicates = {'roi_done': {'type': 'meta_key_exists', 'meta_key': '_roi_done'}}
    if args.secondary_meta_key_override:
        nets['secondary']['meta_key_override'] = sec_key
    if conditional:
        ter_key = args.tertiary_meta_key
        nets['tertiary'] = {'axnet': axnet_path(args.tertiary), 'axnet_config': _axnet_config([stage_cores[2]]),
                            'meta_key_override': ter_key}
        predicates['roi_gate'] = {'type': 'kpts_conf_gt', 'meta_key': sec_key,
                                  'indices': _int_list(args.keypoint_indices), 'value': args.keypoint_threshold}
        nodes.append({'id': 'secondary', 'type': 'net', 'net': 'secondary', 'next': 'gate'})
        nodes.append({'id': 'gate', 'type': 'condition', 'predicate': 'roi_gate', 'then': 'tertiary', 'else': 'collect'})
        nodes.append({'id': 'tertiary', 'type': 'net', 'net': 'tertiary', 'next': 'collect'})
        cls_key = [sec_key, ter_key]
    else:
        nodes.append({'id': 'secondary', 'type': 'net', 'net': 'secondary', 'next': 'collect'})
        cls_key = sec_key
    nodes.append({'id': 'collect', 'type': 'roi_collect', 'det_meta_key': det_key, 'cls_meta_key': cls_key, 'next': 'loop_guard'})
    nodes.append({'id': 'loop_guard', 'type': 'loop_guard', 'until': 'roi_done', 'continue_to': 'roi_iter',
                  'exit_to': 'out', 'max_iters': 50})
    nodes.append({'id': 'out', 'type': 'sink'})
    entry = {'id': args.pipeline_id, 'interface': 'grpc', 'port': args.port, 'im_decode_output_format': 'BGR',
             'timeout': 60, 'graph': {'entry': 'detect', 'nodes': nodes}}
    if args.pin:
        pin = server.pin_groups([sorted(claimed)], CORES_PER_DEVICE)[0]
        entry['taskset_cpus'] = pin['taskset_cpus']
        if pin['membind'] is not None:
            entry['membind'] = pin['membind']
    entry.update(_pipeline_tuning(args))
    return _document(nets, [entry], predicates)
