"""Compile, upload, launch, stop and inspect pipelines through the host server.

Compilation runs locally with the client's PipelineCompiler; a manifest.json written next to the specs carries the state between `compile`, `upload` and `launch`.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from . import server
from .server import ServerError, UsageError, api, log

_CLIENT = Path(__file__).resolve().parents[2]
MANIFEST = 'manifest.json'
STALE_S = 10.0


def _compiler():
    """Import the client's config loader and pipeline compiler.

    Adds client/compiler and client/configs/utils to sys.path on first use.

    Returns:
        tuple: (load_config, PipelineCompiler).
    """
    for sub in ('compiler', 'configs/utils'):
        p = str(_CLIENT / sub)
        if p not in sys.path:
            sys.path.insert(0, p)
    from config_schema import load_config
    from pipeline import PipelineCompiler
    return load_config, PipelineCompiler


def _ensure_sdk_root() -> str:
    """Make sure SDK_ROOT is set in the environment, asking the server when it is not.

    Returns:
        str: The SDK root path.
    """
    if not os.environ.get('SDK_ROOT'):
        os.environ['SDK_ROOT'] = api('GET', '/sdk-root').json()['sdk_root']
    return os.environ['SDK_ROOT']


def doc_id_for(pipeline_ids: list[str]) -> str:
    """Derive a filesystem-safe name for a set of pipelines.

    Args:
        pipeline_ids (list[str]): Pipeline ids; must not be empty.

    Returns:
        str: The first id, plus `_plus<N>` for N further ids, with characters outside A-Za-z0-9_- replaced by `-`, at most 100 characters.
    """
    base = pipeline_ids[0] if len(pipeline_ids) == 1 else f'{pipeline_ids[0]}_plus{len(pipeline_ids) - 1}'
    return re.sub(r'[^A-Za-z0-9_-]', '-', base)[:100]


def compile_config(config: str, out_dir: str | None) -> Path:
    """Validate a config YAML and compile it into pipeline specs.

    Patches the meta_key of every net that sets meta_key_override on the server before compiling, then writes the specs and a manifest.json to the output directory.

    Args:
        config (str): Path to the config YAML.
        out_dir (str | None): Output directory. Defaults to compiled/<doc id>.

    Returns:
        Path: The output directory.

    Raises:
        UsageError: If the file is missing or the config is rejected.
    """
    if not Path(config).is_file():
        raise UsageError(f'config not found: {config}')
    _ensure_sdk_root()
    load_config, PipelineCompiler = _compiler()
    try:
        cfg = load_config(config)
    except Exception as exc:
        raise UsageError(f'config rejected: {str(exc)[:600]}') from exc
    for name, net in cfg.nets.items():
        if net.meta_key_override:
            model = Path(net.axnet).stem
            res = api('POST', '/prebuilt-models/patch-meta-key', json={'name': model, 'meta_key': net.meta_key_override}).json()
            log(f'net {name} ({model}): meta_key_override {net.meta_key_override!r} patched={res.get("patched")}')
    doc_id = doc_id_for([p.id for p in cfg.pipelines])
    out = Path(out_dir or f'compiled/{doc_id}')
    out.mkdir(parents=True, exist_ok=True)
    specs = PipelineCompiler(cfg, output_dir=out).compile_all()
    manifest = {'doc_id': doc_id, 'specs': [
        {'pipeline_id': s.pipeline_id, 'port': s.port, 'file': Path(s.pipeline_json_path).name,
         'taskset_cpus': s.taskset_cpus, 'membind': s.membind} for s in specs]}
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2))
    for s in manifest['specs']:
        log(f'compiled {s["pipeline_id"]} port {s["port"]} taskset={s["taskset_cpus"]} membind={s["membind"]} -> {out / s["file"]}')
    return out


def _manifest(directory: str) -> dict:
    """Load manifest.json from a compiled directory.

    Raises:
        UsageError: If the manifest does not exist.
    """
    path = Path(directory) / MANIFEST
    if not path.is_file():
        raise UsageError(f'{directory} has no {MANIFEST}: run `compile` first')
    return json.loads(path.read_text())


def upload(directory: str) -> dict:
    """Upload each compiled spec to the server and record its saved path in the manifest.

    Args:
        directory (str): Output directory of `compile`.

    Returns:
        dict: The updated manifest.
    """

    manifest = _manifest(directory)
    for spec in manifest['specs']:
        body = {'pipeline_id': spec['pipeline_id'], 'filename': spec['file'],
                'spec_content': (Path(directory) / spec['file']).read_text()}
        spec['saved_path'] = api('POST', '/pipeline-spec', json=body).json()['saved_path']
        log(f'uploaded {spec["pipeline_id"]} -> {spec["saved_path"]}')
    (Path(directory) / MANIFEST).write_text(json.dumps(manifest, indent=2))
    return manifest


def launch(directory: str) -> list[str]:
    """Launch every uploaded pipeline.

    Args:
        directory (str): Output directory of `compile`, after `upload`.

    Returns:
        list[str]: One `host:port` endpoint per pipeline.

    Raises:
        UsageError: If a spec has not been uploaded yet.
    """
    manifest = _manifest(directory)
    host = urlparse(server.require_env()[0]).hostname
    endpoints = []
    for spec in manifest['specs']:
        if not spec.get('saved_path'):
            raise UsageError(f'{spec["pipeline_id"]} is not uploaded yet: run `upload {directory}` first')
        body = {'pipeline_id': spec['pipeline_id'], 'port': spec['port'], 'spec_path': spec['saved_path'],
                'taskset_cpus': spec['taskset_cpus'], 'membind': spec['membind']}
        res = api('POST', '/pipelines/launch', timeout=200.0, json=body).json()
        log(f'launched {spec["pipeline_id"]} pid {res["pid"]} port {res["port"]}')
        endpoints.append(f'{host}:{res["port"]}')
    return endpoints


def pipeline_ids(directory: str | None, ids: str | None) -> list[str]:
    """Resolve pipeline ids from --ids or from a compiled directory.

    Args:
        directory (str | None): Compiled directory holding a manifest.
        ids (str | None): Comma-separated ids; takes precedence over `directory`.

    Returns:
        list[str]: The pipeline ids.

    Raises:
        UsageError: If neither argument is given.
    """
    if ids:
        return [i for i in ids.split(',') if i]
    if directory:
        return [s['pipeline_id'] for s in _manifest(directory)['specs']]
    raise UsageError('give a compiled directory or --ids a,b')


def down(ids: list[str]) -> None:
    """Stop each named pipeline and log whether it was running."""
    for pid in ids:
        res = api('POST', '/pipelines/shutdown', timeout=60.0, json={'pipeline_id': pid}).json()
        log(f'{pid}: ' + ('stopped' if res.get('stopped') else 'not running (not started by this server)'))


def status(ids: list[str], wait_s: float = 0.0) -> bool:
    """Print queue stats for each pipeline.

    A stats line older than STALE_S seconds counts as missing (it is left over from an earlier run). Each pipeline is polled once a second for up to `wait_s` seconds.

    Args:
        ids (list[str]): Pipeline ids.
        wait_s (float, optional): Seconds to wait for fresh stats per pipeline. Defaults to 0.0.

    Returns:
        bool: True if every pipeline has fresh stats and reports healthy.
    """
    ok = True
    for pid in ids:
        deadline = time.monotonic() + wait_s
        while True:
            try:
                s = api('GET', f'/pipelines/{pid}/queue-stats').json()
                reason = f'only a stale stats line from {s["stats_age_s"]:.0f}s ago (an earlier run)'
                if s['stats_age_s'] <= STALE_S:
                    break
                raise ServerError(reason)
            except ServerError as exc:
                if time.monotonic() >= deadline:
                    s = None
                    reason = str(exc)[:120]
                    break
                time.sleep(1.0)
        if s is None:
            print(f'{pid}: no stats ({reason})')
            ok = False
            continue
        print(f'{pid}: healthy={s["healthy"]} frames={s["total_frames"]} dropped={s["dropped_frames"]} '
              f'avg_latency_ms={s["avg_latency_ms"]:.1f} pending={s["pending_requests"]} stats_age_s={s["stats_age_s"]}')
        ok = ok and s['healthy']
    return ok
