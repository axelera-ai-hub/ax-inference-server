#!/usr/bin/env python3

"""Regenerate and post-patch .axnet pipeline files by running the SDK's inference.py.

Runs one short inference per net in a server config so the SDK writes its .axnet file, patches known SDK gaps in that file, and checks it with a smoke test. Exposes regenerate(), smoke_test() and a CLI (main).
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "client" / "configs" / "utils"))

from config_schema import load_config


def _axelera_framework_value(sdk_root: str) -> str:
    """Return the value to export as AXELERA_FRAMEWORK for an SDK root.

    Paths that contain "llm" are replaced by a stable symlink in the temp directory (named from a SHA-1 of the path), which is created or repointed as needed. The code does not state why such paths are aliased.

    Args:
        sdk_root (str): Absolute path to the SDK checkout.

    Returns:
        str: sdk_root unchanged, or the alias symlink path.
    """
    if "llm" not in sdk_root:
        return sdk_root
    alias = Path(tempfile.gettempdir()) / f"axfw-{hashlib.sha1(sdk_root.encode()).hexdigest()[:12]}"
    real = Path(sdk_root)
    if not alias.is_symlink() or alias.resolve() != real.resolve():
        alias.unlink(missing_ok=True)
        alias.symlink_to(real)
    return str(alias)


def _model_name_from_axnet_path(axnet_path: str) -> str:
    """Return the model name, taken as the name of the .axnet file's parent directory."""
    return Path(axnet_path).parent.name


def _find_labels_path_for_model(model_name: str) -> str | None:
    """Look up a model's labels_path in the deployment YAMLs under server/models.

    Scans models/*/deployment/*.yaml, skipping unreadable files, and returns the first dataset labels_path of the document whose name equals model_name.

    Args:
        model_name (str): Model name as found in the YAML "name" key.

    Returns:
        str | None: The labels path, or None if no deployment YAML provides one.
    """
    models_dir = Path(__file__).parent.parent
    for dep_yaml in models_dir.glob("*/deployment/*.yaml"):
        try:
            doc = yaml.safe_load(dep_yaml.read_text())
        except Exception:
            continue
        if not isinstance(doc, dict) or doc.get("name") != model_name:
            continue
        for ds in (doc.get("datasets") or {}).values():
            if isinstance(ds, dict) and ds.get("labels_path"):
                return ds["labels_path"]
    return None


def _patch_classlabels_if_missing(axnet_path: str, model_name: str) -> bool:

    """Add a classlabels_file option to classification postprocess lines that lack one.

    For each postprocess line using libdecode_classification.so, the matching *_options line gets "classlabels_file:<labels_path>;" appended, using the path from the model's deployment YAML. Options lines that already have it, or models with no labels path, are left alone. Rewrites the file and logs to stderr only when something changed. Works around the SDK not emitting this option.

    Args:
        axnet_path (str): Path to the .axnet file, edited in place.
        model_name (str): Model name used to find the labels path.

    Returns:
        bool: True if the file was modified.
    """
    lines = Path(axnet_path).read_text().splitlines()
    changed = False
    for i, line in enumerate(lines):
        if not line.startswith("postprocess") or "_lib=" not in line:
            continue
        if "libdecode_classification.so" not in line:
            continue
        prefix = line.split("_lib=")[0]
        opts_key = f"{prefix}_options="
        for j, oline in enumerate(lines):
            if not oline.startswith(opts_key):
                continue
            if "classlabels_file:" in oline:
                continue
            labels_path = _find_labels_path_for_model(model_name)
            if not labels_path:
                continue
            sep = "" if oline.endswith(";") else ";"
            lines[j] = oline + sep + f"classlabels_file:{labels_path};"
            changed = True

    if changed:
        Path(axnet_path).write_text("\n".join(lines) + "\n")
        print(f"axnet: patched classlabels_file into {axnet_path} "
              f"(SDK gap -- see _patch_classlabels_if_missing docstring)", file=sys.stderr)
    return changed


def _patch_meta_key_if_requested(axnet_path: str, override: str) -> bool:

    """Replace the meta_key value in postprocess options lines.

    Only postprocess*_options lines that already contain "meta_key:<value>;" are rewritten, so that cascaded nets do not collide on the same meta key. Lines already using the override are untouched. Rewrites the file and logs to stderr only when something changed.

    Args:
        axnet_path (str): Path to the .axnet file, edited in place.
        override (str): New meta_key value.

    Returns:
        bool: True if the file was modified.
    """
    lines = Path(axnet_path).read_text().splitlines()
    changed = False
    for i, line in enumerate(lines):
        if not line.startswith("postprocess") or "_options=" not in line:
            continue
        if f"meta_key:{override};" in line:
            continue
        if "meta_key:" not in line:
            continue
        prefix, _, rest = line.partition("meta_key:")
        _, sep, remainder = rest.partition(";")
        if not sep:
            continue
        lines[i] = f"{prefix}meta_key:{override};{remainder}"
        changed = True

    if changed:
        Path(axnet_path).write_text("\n".join(lines) + "\n")
        print(f"axnet: patched meta_key -> {override!r} into {axnet_path} "
              f"(cascade meta_key collision -- see _patch_meta_key_if_requested docstring)",
              file=sys.stderr)
    return changed


_PREPROCESS_LINE_RE = re.compile(r"^preprocess(\d+)_(.+)$")


def _patch_colorconvert_if_opencl_disabled(axnet_path: str, opencl_enabled: bool) -> bool:

    """Insert a CPU colorconvert (format:bgra) stage as preprocess0 when OpenCL is off.

    Existing preprocessN_ lines are renumbered to N+1 and "preprocess0_lib=libtransform_colorconvert.so" with "preprocess0_options=format:bgra" is inserted before them. Does nothing if OpenCL is enabled, the stage already exists, or the file has no preprocess lines. Works around a channel-count gap when the SDK runs with --disable-opencl.

    Args:
        axnet_path (str): Path to the .axnet file, edited in place.
        opencl_enabled (bool): Whether the net was generated with OpenCL enabled.

    Returns:
        bool: True if the file was modified.
    """
    if opencl_enabled:
        return False
    lines = Path(axnet_path).read_text().splitlines()
    if any(l.startswith("preprocess0_lib=libtransform_colorconvert.so") for l in lines):
        return False

    renumbered = []
    first_preprocess_idx = None
    for i, line in enumerate(lines):
        m = _PREPROCESS_LINE_RE.match(line)
        if not m:
            renumbered.append(line)
            continue
        if first_preprocess_idx is None:
            first_preprocess_idx = len(renumbered)
        n, tail = m.groups()
        renumbered.append(f"preprocess{int(n) + 1}_{tail}")

    if first_preprocess_idx is None:
        return False

    renumbered[first_preprocess_idx:first_preprocess_idx] = [
        "preprocess0_lib=libtransform_colorconvert.so",
        "preprocess0_options=format:bgra",
    ]
    Path(axnet_path).write_text("\n".join(renumbered) + "\n")
    print(f"axnet: patched colorconvert(format:bgra) as preprocess0 into {axnet_path} "
          f"(--disable-opencl channel-count gap -- see "
          f"_patch_colorconvert_if_opencl_disabled docstring)", file=sys.stderr)
    return True


_ASYNC_EXECUTOR_FLAG_SUPPORTED: dict[tuple[str, str], bool] = {}

_ASYNC_UNSUPPORTED_SIGNATURES = ("Failed to find property async_mode", "unrecognized arguments")


def _mark_async_unsupported(sdk_root: str, sdk_venv: str) -> None:
    """Record that this SDK root and venv do not support --enable-async-executor."""
    _ASYNC_EXECUTOR_FLAG_SUPPORTED[(sdk_root, sdk_venv)] = False


def _regenerate_one(sdk_root: str, sdk_venv: str, opencl_flag: str, axnet_path: str,
                     media: str, frames: int, aipu_cores: int, device: int,
                     meta_key_override: str | None = None, low_latency: bool = True) -> str:
    """Run the SDK's inference.py for one net to regenerate its .axnet, then patch it.

    Deletes the existing .axnet, runs inference.py in a bash subshell with the SDK venv activated (DMABUF and double buffer env vars set, VAAPI and display disabled), and applies the classlabels, meta_key and colorconvert patches. --enable-async-executor is tried first unless this SDK was previously found not to support it; on failure with a matching stderr signature the run is retried without it and the result is cached in _ASYNC_EXECUTOR_FLAG_SUPPORTED.

    Args:
        sdk_root (str): SDK checkout path.
        sdk_venv (str): Venv directory relative to sdk_root.
        opencl_flag (str): "--enable-opencl" or "--disable-opencl", passed to inference.py.
        axnet_path (str): Expected output .axnet path; its parent directory name is the model name.
        media (str): Media file to run inference on.
        frames (int): Number of frames to process.
        aipu_cores (int): Value for --aipu-cores.
        device (int): Device index for -d.
        meta_key_override (str | None, optional): If set, patch meta_key to this value. Defaults to None.
        low_latency (bool, optional): Pass --low-latency instead of --no-low-latency. Defaults to True.

    Returns:
        str: axnet_path.

    Raises:
        subprocess.CalledProcessError: If inference.py fails (its output is echoed to stderr).
        RuntimeError: If no .axnet exists at axnet_path afterwards.
    """
    model_name = _model_name_from_axnet_path(axnet_path)

    Path(axnet_path).unlink(missing_ok=True)

    env = dict(os.environ)
    env["AXELERA_USE_DMABUF"] = "3"
    env["AXELERA_USE_DOUBLE_BUFFER"] = "1"

    low_latency_flag = "--low-latency" if low_latency else "--no-low-latency"

    def _inference_cmd(with_async: bool) -> str:
        async_flag = " --enable-async-executor" if with_async else ""
        return (
            f'source "{sdk_root}/{sdk_venv}/bin/activate" && '
            f'export AXELERA_FRAMEWORK="{_axelera_framework_value(sdk_root)}" && '
            f'export LD_LIBRARY_PATH="{sdk_root}/operators/lib:${{LD_LIBRARY_PATH:-}}" && '
            f'exec python3 "{sdk_root}/inference.py" '
            f'-d{device} --frames {frames} --aipu-cores={aipu_cores} '
            f'--disable-vaapi --no-display {opencl_flag} {low_latency_flag}{async_flag} '
            f'"{model_name}" "{media}" -v'
        )

    want_async = _ASYNC_EXECUTOR_FLAG_SUPPORTED.get((sdk_root, sdk_venv), True)
    print(f"axnet: regenerating {axnet_path} ({opencl_flag}, {low_latency_flag}, "
          f"async-executor={'on' if want_async else 'disabled (previously found unsupported here)'})", file=sys.stderr)
    result = subprocess.run(["bash", "-c", _inference_cmd(want_async)], cwd=sdk_root, env=env,
                            capture_output=True, text=True)
    if (result.returncode != 0 and want_async
            and any(sig in result.stderr for sig in _ASYNC_UNSUPPORTED_SIGNATURES)):
        print(f"axnet: {sdk_root}/{sdk_venv} doesn't actually support "
              "--enable-async-executor -- retrying without", file=sys.stderr)
        _mark_async_unsupported(sdk_root, sdk_venv)
        Path(axnet_path).unlink(missing_ok=True)
        result = subprocess.run(["bash", "-c", _inference_cmd(False)], cwd=sdk_root, env=env,
                                capture_output=True, text=True)
    elif result.returncode == 0:
        _ASYNC_EXECUTOR_FLAG_SUPPORTED[(sdk_root, sdk_venv)] = want_async
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise subprocess.CalledProcessError(result.returncode, result.args,
                                             output=result.stdout, stderr=result.stderr)

    if not Path(axnet_path).exists():
        raise RuntimeError(f".axnet not produced at {axnet_path}")
    _patch_classlabels_if_missing(axnet_path, model_name)
    if meta_key_override:
        _patch_meta_key_if_requested(axnet_path, meta_key_override)
    _patch_colorconvert_if_opencl_disabled(axnet_path, opencl_flag == "--enable-opencl")
    return axnet_path


def regenerate(cfg, media: str, frames: int, aipu_cores: int, device: int,
                low_latency: bool = True) -> list[str]:
    """Regenerate the .axnet of every net in a server config.

    Uses global_settings.use_axinference_net_opencl, defaulting to "--enable-opencl".

    Args:
        cfg: Loaded server config exposing global_settings and nets.
        media (str): Media file to run inference on.
        frames (int): Number of frames to process.
        aipu_cores (int): Value for --aipu-cores.
        device (int): Device index.
        low_latency (bool, optional): Use the low-latency profile. Defaults to True.

    Returns:
        list[str]: The regenerated .axnet paths, one per net.

    Raises:
        RuntimeError: If sdk_root is unresolved or the config has no nets.
    """
    g = cfg.global_settings
    sdk_root = g.sdk_root
    if not sdk_root:
        raise RuntimeError("sdk_root could not be resolved (set global.sdk_root or $SDK_ROOT)")
    if not cfg.nets:
        raise RuntimeError("config has no nets: to regenerate")

    opencl_flag = g.use_axinference_net_opencl or "--enable-opencl"

    return [
        _regenerate_one(sdk_root, g.sdk_venv, opencl_flag, net.axnet, media, frames, aipu_cores, device,
                         meta_key_override=net.meta_key_override, low_latency=low_latency)
        for net in cfg.nets.values()
    ]


def smoke_test(axnet_path: str, opencl_enabled: bool, expect_async_mode: bool = True,
               expect_double_buffer_false: bool = True) -> None:
    """Assert that a regenerated .axnet has the expected async, buffering and OpenCL settings.

    Checks for async_mode=True (optional), double_buffer=False/True, and that the preprocess libs match the OpenCL mode: libtransform_resize_cl.so when enabled; otherwise no *_cl.so, libtransform_resize.so present and the colorconvert preprocess0 patch applied. Prints a PASS line to stderr.

    Args:
        axnet_path (str): Path to the .axnet file.
        opencl_enabled (bool): Whether OpenCL preprocess libs are expected.
        expect_async_mode (bool, optional): Require "async_mode=True". Defaults to True.
        expect_double_buffer_false (bool, optional): Expect "double_buffer=False" instead of "double_buffer=True". Defaults to True.

    Raises:
        AssertionError: If any expectation is not met.
    """
    text = Path(axnet_path).read_text()
    lines = text.splitlines()

    if expect_async_mode and "async_mode=True" not in lines:
        raise AssertionError(f"async_mode=True not found in {axnet_path}")
    expected_db_line = "double_buffer=False" if expect_double_buffer_false else "double_buffer=True"
    if expected_db_line not in lines:
        raise AssertionError(f"{expected_db_line} not found in {axnet_path}")

    lib_lines = [l for l in lines if "_lib=" in l]
    has_cl_lib = any("_cl.so" in l for l in lib_lines)
    if opencl_enabled:
        if not any("libtransform_resize_cl.so" in l for l in lib_lines):
            raise AssertionError(
                f"--enable-opencl requested but no libtransform_resize_cl.so found in {axnet_path}"
            )
    else:
        if has_cl_lib:
            raise AssertionError(
                f"--disable-opencl requested but a *_cl.so preprocess lib is present in {axnet_path}"
            )
        if not any("libtransform_resize.so" in l for l in lib_lines):
            raise AssertionError(
                f"--disable-opencl requested but expected CPU-path libtransform_resize.so "
                f"not found in {axnet_path}"
            )
        if "preprocess0_lib=libtransform_colorconvert.so" not in lines:
            raise AssertionError(
                f"--disable-opencl requested but the colorconvert(format:bgra) patch "
                f"(_patch_colorconvert_if_opencl_disabled) wasn't applied to {axnet_path}"
            )

    print(f"axnet: smoke test PASS ("
          f"{'async_mode=True, ' if expect_async_mode else '(async_mode check skipped -- unsupported by this inference.py), '}"
          f"{expected_db_line}, "
          f"opencl={'enabled' if opencl_enabled else 'disabled'} confirmed via preprocess libs)",
          file=sys.stderr)


def main() -> None:
    """Parse CLI arguments, regenerate the config's .axnet files and smoke-test each one.

    Prints "PASS: <paths>" on success.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("config", help="path to a ServerConfig YAML")
    ap.add_argument("--media", required=True, help="video file to run inference.py against")
    ap.add_argument("--frames", type=int, default=1)
    ap.add_argument("--aipu-cores", type=int, default=4)
    ap.add_argument("-d", "--device", type=int, default=0)
    ap.add_argument(
        "--low-latency", dest="low_latency", action="store_true", default=True,
        help="(default) disables double buffering and forces batch_size==1 -- this "
        "project's production profile (see should_use_async_pipeline in the "
        "vendor's AxInference.cpp: real callback + batch-dim==1 is what actually "
        "selects the async executor, independent of any flag here).",
    )
    ap.add_argument(
        "--no-low-latency", dest="low_latency", action="store_false",
        help="Enables double buffering -- not a recommended production setting, "
        "and not an independently toggleable property from batch_size either "
        "(see --low-latency's own help text for the batch_size==1 interaction).",
    )
    args = ap.parse_args()

    cfg = load_config(args.config)
    axnet_paths = regenerate(cfg, args.media, args.frames, args.aipu_cores, args.device,
                              low_latency=args.low_latency)
    opencl_enabled = (cfg.global_settings.use_axinference_net_opencl or "--enable-opencl") == "--enable-opencl"
    expect_async_mode = _ASYNC_EXECUTOR_FLAG_SUPPORTED.get(
        (cfg.global_settings.sdk_root, cfg.global_settings.sdk_venv), True
    )
    for axnet_path in axnet_paths:
        smoke_test(axnet_path, opencl_enabled, expect_async_mode=expect_async_mode,
                   expect_double_buffer_false=args.low_latency)
    print(f"PASS: {', '.join(axnet_paths)}")


if __name__ == "__main__":
    main()
