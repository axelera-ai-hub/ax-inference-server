"""FastAPI host API for the deployment host (run as ``host_server:app`` under uvicorn).

Exposes the ``/api/v1`` endpoints that remote clients use to upload pipeline specs and YAML, inspect and maintain Axelera devices, provision models, launch and stop axinferencenet_grpc pipelines and vLLM servers, and read AxMonitor telemetry. Every endpoint except ``/api/v1/health`` requires an ``X-API-Key`` header equal to ``DEPLOYMENT_API_KEY``.

Note:
    Launched processes, monitor buffers and progress state are held in memory and are lost when the server restarts. Most endpoints need ``SDK_ROOT`` in the environment.
"""

from __future__ import annotations

import atexit
import glob
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Literal, Optional, Union

import yaml
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, UploadFile, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator

load_dotenv()

DEPLOYMENT_DIR = Path(__file__).resolve().parent
# Not read anywhere else in this module.
SETUP_SCRIPT_PATH = Path(os.environ.get("SETUP_SCRIPT_PATH", DEPLOYMENT_DIR / "setup.sh"))
YAML_UPLOAD_DIR = Path(os.environ.get("YAML_UPLOAD_DIR", DEPLOYMENT_DIR / "uploaded_yaml"))

import sys as _sys
_REPO_ROOT = DEPLOYMENT_DIR.parent
_AXNET_DIR = _REPO_ROOT / "server" / "models" / "utils"
if str(_AXNET_DIR) not in _sys.path:
    _sys.path.insert(0, str(_AXNET_DIR))
import axnet as _axnet
import launch_remote

AXINFERENCENET_BIN_PATH = Path(
    os.environ.get("AXINFERENCENET_BIN_PATH", _REPO_ROOT / "server" / "build" / "axinferencenet_grpc")
)

_MODEL_PROVISION_MEDIA = _REPO_ROOT / "client" / "assets" / "test_images" / "traffic_frame_480p.jpg"
_MODEL_PROVISION_FRAMES = 1
# Not read anywhere else in this module.
ALLOWED_SDK_DEST_PREFIXES = [
    p.strip() for p in os.environ.get("ALLOWED_SDK_DEST_PREFIXES", "/opt/sdk").split(",") if p.strip()
]

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# _SAFE_REF_RE and _SAFE_REPO_URL_RE are not used in this module.
_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9_./-]{1,200}$")
_SAFE_REPO_URL_RE = re.compile(
    r"^(https://[A-Za-z0-9_./-]+\.git|git@[A-Za-z0-9_.-]+:[A-Za-z0-9_./-]+\.git)$"
)
_SAFE_PIPELINE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_SAFE_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def require_api_key(api_key: Optional[str] = Depends(API_KEY_HEADER)) -> None:
    """Check the ``X-API-Key`` header against ``DEPLOYMENT_API_KEY`` (FastAPI dependency).

    Args:
        api_key (Optional[str]): Value of the ``X-API-Key`` header, if sent.

    Raises:
        HTTPException: 500 if ``DEPLOYMENT_API_KEY`` is not set, 401 if the key is missing or wrong.
    """
    expected = os.environ.get("DEPLOYMENT_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DEPLOYMENT_API_KEY is not configured on the server",
        )
    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing X-API-Key")


app = FastAPI(title="inference_server deployment host API")


@app.get("/api/v1/health")
def health() -> dict:
    """Report liveness; the only endpoint that needs no API key."""
    return {"status": "ok"}


class YamlUploadResponse(BaseModel):
    """Result of a YAML upload.

    Attributes:
        saved_path (str): Path of the stored file on the host.
    """

    saved_path: str


@app.post("/api/v1/yaml", response_model=YamlUploadResponse, dependencies=[Depends(require_api_key)])
async def upload_yaml(file: UploadFile) -> YamlUploadResponse:
    """Store an uploaded YAML file in ``YAML_UPLOAD_DIR``, overwriting a file of the same name.

    Only the base name of the uploaded filename is used. The content must parse with ``yaml.safe_load``.

    Args:
        file (UploadFile): The uploaded file; its name must end in ``.yaml`` or ``.yml``.

    Returns:
        YamlUploadResponse: Where the file was saved.

    Raises:
        HTTPException: 400 if the name has the wrong extension or the content is not valid YAML.
    """
    name = Path(file.filename or "").name
    if not name or not (name.endswith(".yaml") or name.endswith(".yml")):
        raise HTTPException(status_code=400, detail="filename must end in .yaml or .yml")

    body = await file.read()
    try:
        yaml.safe_load(body)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"not valid YAML: {exc}") from exc

    YAML_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = YAML_UPLOAD_DIR / name
    dest.write_bytes(body)
    return YamlUploadResponse(saved_path=str(dest))


def _require_sdk_root() -> Path:
    """Return ``SDK_ROOT`` as a Path.

    Raises:
        HTTPException: 500 if ``SDK_ROOT`` is unset or is not a directory.
    """
    sdk_root = os.environ.get("SDK_ROOT")
    if not sdk_root:
        raise HTTPException(status_code=500, detail="SDK_ROOT is not configured on this server")
    path = Path(sdk_root)
    if not path.is_dir():
        raise HTTPException(status_code=500, detail=f"SDK_ROOT={sdk_root} is not a directory on this server")
    return path


class SdkRootResponse(BaseModel):
    """The configured SDK root.

    Attributes:
        sdk_root (str): Value of ``SDK_ROOT`` on this host.
    """

    sdk_root: str


@app.get("/api/v1/sdk-root", response_model=SdkRootResponse, dependencies=[Depends(require_api_key)])
def get_sdk_root() -> SdkRootResponse:
    """Return the SDK root directory configured on this host."""
    return SdkRootResponse(sdk_root=str(_require_sdk_root()))


def _axelera_framework_value(sdk_root: Path) -> str:
    """Return the value to export as ``AXELERA_FRAMEWORK`` for SDK tools.

    A path containing the substring ``llm`` is returned as a symlink in the temp directory named ``axfw-<sha1 prefix of the path>`` that points at the SDK root (created or repointed as needed). Any other path is returned unchanged.

    Args:
        sdk_root (Path): The SDK root directory.

    Returns:
        str: The SDK root or its symlink alias.
    """
    if "llm" not in str(sdk_root):
        return str(sdk_root)
    alias = Path(tempfile.gettempdir()) / f"axfw-{hashlib.sha1(str(sdk_root).encode()).hexdigest()[:12]}"
    if not alias.is_symlink() or alias.resolve() != sdk_root.resolve():
        alias.unlink(missing_ok=True)
        alias.symlink_to(sdk_root)
    return str(alias)


class VisionModelInfo(BaseModel):
    """A compiled vision model found under ``SDK_ROOT/build``.

    Attributes:
        name (str): Model directory name.
        axnet_path (str): Path of its ``.axnet`` file, written with a literal ``${SDK_ROOT}`` prefix.
    """

    name: str
    axnet_path: str


class VlmModelInfo(BaseModel):
    """A VLM artifact directory containing ``vision`` and ``text`` subdirectories.

    Attributes:
        name (str): Directory path relative to the SDK root (``.`` for the root itself).
        artifact_path (str): Directory path written with a literal ``${SDK_ROOT}`` prefix.
        vision_subdir (str): Always ``vision``.
        text_subdir (str): Always ``text``.
    """

    name: str
    artifact_path: str
    vision_subdir: str
    text_subdir: str


class ModelsResponse(BaseModel):
    """Models discovered under the SDK root.

    Attributes:
        vision_models (list[VisionModelInfo]): Models with a built ``.axnet``.
        vlm_models (list[VlmModelInfo]): VLM artifact directories.
    """

    vision_models: list[VisionModelInfo]
    vlm_models: list[VlmModelInfo]


@app.get("/api/v1/models", response_model=ModelsResponse, dependencies=[Depends(require_api_key)])
def list_models() -> ModelsResponse:
    """List vision and VLM models found under the SDK root.

    A vision model is a directory ``build/<name>/`` holding ``<name>.axnet``. A VLM model is the SDK root, a child of it, or a grandchild of it that contains both ``vision/`` and ``text/`` directories.

    Returns:
        ModelsResponse: The discovered models.
    """
    sdk_root = _require_sdk_root()

    vision_models = []
    build_dir = sdk_root / "build"
    if build_dir.is_dir():
        for model_dir in sorted(p for p in build_dir.iterdir() if p.is_dir()):
            axnet = model_dir / f"{model_dir.name}.axnet"
            if axnet.is_file():
                vision_models.append(VisionModelInfo(
                    name=model_dir.name,
                    axnet_path=f"${{SDK_ROOT}}/build/{model_dir.name}/{model_dir.name}.axnet",
                ))

    vlm_models = []
    candidates = [sdk_root] + [p for p in sdk_root.iterdir() if p.is_dir()] if sdk_root.is_dir() else []
    seen = set()
    for base in candidates:
        if not base.is_dir():
            continue
        for candidate in [base] + [p for p in base.iterdir() if p.is_dir()]:
            if candidate in seen or not candidate.is_dir():
                continue
            seen.add(candidate)
            if (candidate / "vision").is_dir() and (candidate / "text").is_dir():
                rel = candidate.relative_to(sdk_root)
                artifact_path = "${SDK_ROOT}" if str(rel) == "." else f"${{SDK_ROOT}}/{rel}"
                vlm_models.append(VlmModelInfo(
                    name=str(rel),
                    artifact_path=artifact_path,
                    vision_subdir="vision",
                    text_subdir="text",
                ))

    return ModelsResponse(vision_models=vision_models, vlm_models=vlm_models)


_YAML_NAME_RE = re.compile(r'^name:\s*[\"\']?([\w.\-]+)[\"\']?\s*$', re.MULTILINE)

_PIPELINE_STAGE_RE = re.compile(r'\bpipeline:\s*\n\s*-\s*([A-Za-z0-9_]+):')


class ModelMetaKeyResponse(BaseModel):
    """The meta key of a model-zoo model.

    Attributes:
        meta_key (str): Name of the first stage under ``pipeline:`` in the model YAML.
        source_yaml (str): The YAML path relative to the SDK root.
    """

    meta_key: str
    source_yaml: str


@app.get(
    "/api/v1/models/{name}/meta-key",
    response_model=ModelMetaKeyResponse,
    dependencies=[Depends(require_api_key)],
)
def get_model_meta_key(name: str) -> ModelMetaKeyResponse:
    """Look up a model's meta key in the SDK model zoo (``SDK_ROOT/ax_models``).

    Finds the single YAML whose top-level ``name:`` equals the given name and returns the first stage name listed under its ``pipeline:`` key.

    Args:
        name (str): Model name as declared in the YAML.

    Returns:
        ModelMetaKeyResponse: The meta key and the YAML it came from.

    Raises:
        HTTPException: 500 if ``ax_models`` is missing, 404 if no YAML declares the name, 409 if several do, 422 if the YAML has no pipeline stage.
    """
    sdk_root = _require_sdk_root()

    zoo_dir = sdk_root / "ax_models"
    if not zoo_dir.is_dir():
        raise HTTPException(status_code=500, detail=f"{zoo_dir} does not exist on this server")

    matches: list[Path] = []
    for yaml_path in zoo_dir.rglob("*.yaml"):
        try:
            text = yaml_path.read_text()
        except OSError:
            continue
        name_match = _YAML_NAME_RE.search(text)
        if name_match and name_match.group(1) == name:
            matches.append(yaml_path)

    if not matches:
        raise HTTPException(
            status_code=404,
            detail=f"no model YAML found under {zoo_dir} declaring name: {name}",
        )
    if len(matches) > 1:
        rels = [str(p.relative_to(sdk_root)) for p in matches]
        raise HTTPException(
            status_code=409,
            detail=f"model name {name!r} is ambiguous -- found in multiple YAMLs: {', '.join(rels)}",
        )

    source_yaml = matches[0]
    text = source_yaml.read_text()
    stage_match = _PIPELINE_STAGE_RE.search(text)
    if not stage_match:
        raise HTTPException(
            status_code=422,
            detail=f"no pipeline stage found in {source_yaml.relative_to(sdk_root)} to use as meta_key",
        )

    return ModelMetaKeyResponse(
        meta_key=stage_match.group(1),
        source_yaml=str(source_yaml.relative_to(sdk_root)),
    )


# AIPU cores per Metis device.
CORES_PER_DEVICE = 4
_DEVICE_LINE_RE = re.compile(r"^Device (\d+): (\S+)")


class DeviceInfo(BaseModel):
    """One Metis device reported by ``axdevice -v``.

    Attributes:
        index (int): Device index.
        name (str): Device address as printed by axdevice.
        cores (int): AIPU cores, always ``CORES_PER_DEVICE``.
    """

    index: int
    name: str
    cores: int


class DevicesResponse(BaseModel):
    """Devices present on the host.

    Attributes:
        devices (list[DeviceInfo]): One entry per ``Device N:`` line.
    """

    devices: list[DeviceInfo]


_DEVICES_CACHE_TTL_S = 20.0
# Device list cache keyed by SDK root: (time.monotonic() stamp, response).
_devices_cache: dict[str, tuple[float, "DevicesResponse"]] = {}


def _enumerate_devices(sdk_root: Path) -> DevicesResponse:
    """Run ``axdevice -v`` from the SDK venv and parse the device list.

    Args:
        sdk_root (Path): The SDK root directory.

    Returns:
        DevicesResponse: Devices found, in output order.

    Raises:
        HTTPException: 500 if axdevice is missing or exits non-zero.
    """
    sdk_venv = os.environ.get("SDK_VENV", "venv")
    axdevice = sdk_root / sdk_venv / "bin" / "axdevice"
    if not axdevice.is_file():
        raise HTTPException(status_code=500, detail=f"axdevice not found at {axdevice}")

    env = os.environ.copy()
    env["AXELERA_FRAMEWORK"] = _axelera_framework_value(sdk_root)
    result = subprocess.run(
        [str(axdevice), "-v"], capture_output=True, text=True, env=env, check=False,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"axdevice -v failed: {result.stderr.strip()}")

    devices = []
    for line in result.stdout.splitlines():
        m = _DEVICE_LINE_RE.match(line)
        if m:
            devices.append(DeviceInfo(index=int(m.group(1)), name=m.group(2), cores=CORES_PER_DEVICE))
    return DevicesResponse(devices=devices)


@app.get("/api/v1/devices", response_model=DevicesResponse, dependencies=[Depends(require_api_key)])
def list_devices() -> DevicesResponse:
    """List the Metis devices on this host.

    The result is cached per SDK root for ``_DEVICES_CACHE_TTL_S`` seconds.

    Returns:
        DevicesResponse: The devices.
    """
    sdk_root = _require_sdk_root()

    cached = _devices_cache.get(str(sdk_root))
    if cached is not None and time.monotonic() - cached[0] < _DEVICES_CACHE_TTL_S:
        return cached[1]

    response = _enumerate_devices(sdk_root)
    _devices_cache[str(sdk_root)] = (time.monotonic(), response)
    return response


_AXDEVICE_ACTION_FLAGS = {"refresh": "--refresh", "reload_firmware": "--reload-firmware"}
# Seconds allowed for refresh / reload-firmware; the power-limit step gets _AXDEVICE_POWER_TIMEOUT_S.
_AXDEVICE_ACTION_TIMEOUT_S = 300.0
_AXDEVICE_POWER_TIMEOUT_S = 60.0
_AXDEVICE_LOCK = threading.Lock()


class AxdeviceRequest(BaseModel):
    """Maintenance request for one device.

    Attributes:
        action (Optional[Literal["refresh", "reload_firmware"]]): axdevice operation to run first.
        power_limit_w (Optional[Union[float, Literal["off"]]]): Power limit to set in watts (0 to 500), or ``off``.
        confirm (bool): Must be true; guards against accidental hardware resets.
        allow_busy (bool): Proceed even if axinferencenet processes are running.
    """

    action: Optional[Literal["refresh", "reload_firmware"]] = None
    power_limit_w: Optional[Union[float, Literal["off"]]] = None
    confirm: bool = False
    allow_busy: bool = False

    @field_validator("power_limit_w")
    @classmethod
    def validate_power_limit(cls, v):
        """Reject numeric power limits outside 0 to 500 W."""
        if isinstance(v, float) and not 0 <= v <= 500:
            raise ValueError("power_limit_w must be between 0 and 500 watts, or 'off'")
        return v


class AxdeviceStepResult(BaseModel):
    """Outcome of one axdevice command.

    Attributes:
        step (Literal["refresh", "reload_firmware", "set_power_limit"]): Which step ran.
        command (list[str]): The argv that was executed.
        returncode (Optional[int]): Exit code, or None if the command timed out.
        stdout (str): Captured standard output (partial output on timeout).
        stderr (str): Captured standard error, or a timeout message.
        timed_out (bool): Whether the timeout expired.
    """

    step: Literal["refresh", "reload_firmware", "set_power_limit"]
    command: list[str]
    returncode: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool = False


class AxdeviceResponse(BaseModel):
    """Result of a device maintenance call.

    Attributes:
        device_id (int): The device that was targeted.
        ok (bool): True if every step exited with code 0.
        steps (list[AxdeviceStepResult]): Steps that ran, in order.
        device_before (Optional[str]): The device's ``axdevice -v`` line before the steps.
        device_after (Optional[str]): The same line after the steps.
        power_limit_w_after (Optional[Union[float, Literal["off"]]]): Power limit parsed from ``device_after``.
    """

    device_id: int
    ok: bool
    steps: list[AxdeviceStepResult]
    device_before: Optional[str]
    device_after: Optional[str]
    power_limit_w_after: Optional[Union[float, Literal["off"]]] = None


class AxdeviceStatusResponse(BaseModel):
    """Current status line of one device.

    Attributes:
        device_id (int): The device queried.
        device (Optional[str]): Its ``axdevice -v`` line.
        power_limit_w (Optional[Union[float, Literal["off"]]]): Power limit parsed from that line, if shown.
    """

    device_id: int
    device: Optional[str]
    power_limit_w: Optional[Union[float, Literal["off"]]] = None


_POWER_LIMIT_RE = re.compile(r"\bpower-limit=(off|[0-9]+(?:\.[0-9]+)?)\s*W?\b")


def _parse_power_limit(line: Optional[str]) -> Optional[Union[float, str]]:
    """Extract the ``power-limit=`` value from an ``axdevice -v`` device line.

    Args:
        line (Optional[str]): The device line.

    Returns:
        Optional[Union[float, str]]: Watts as a float, ``"off"``, or None if the line has no power limit.
    """
    m = _POWER_LIMIT_RE.search(line or "")
    if not m:
        return None
    return "off" if m.group(1) == "off" else float(m.group(1))


def _axdevice_bin(sdk_root: Path) -> Path:
    """Return the path of the axdevice binary in the SDK venv.

    Raises:
        HTTPException: 500 if the binary does not exist.
    """
    axdevice = sdk_root / os.environ.get("SDK_VENV", "venv") / "bin" / "axdevice"
    if not axdevice.is_file():
        raise HTTPException(status_code=500, detail=f"axdevice not found at {axdevice}")
    return axdevice


def _device_line(axdevice: Path, env: dict, device_id: int) -> Optional[str]:
    """Return the stripped ``axdevice -v`` output line for one device, or None if it is not listed.

    The exit code of axdevice is not checked.
    """
    result = subprocess.run([str(axdevice), "-v"], capture_output=True, text=True, env=env, check=False)
    for line in result.stdout.splitlines():
        m = _DEVICE_LINE_RE.match(line)
        if m and int(m.group(1)) == device_id:
            return line.strip()
    return None


def _run_axdevice_step(step: str, cmd: list[str], env: dict, timeout_s: float) -> AxdeviceStepResult:
    """Run one axdevice command and capture its result.

    Args:
        step (str): Step name recorded in the result.
        cmd (list[str]): Command to execute.
        env (dict): Environment for the child process.
        timeout_s (float): Seconds before the command is abandoned.

    Returns:
        AxdeviceStepResult: The result; ``returncode`` is None and ``timed_out`` is true on timeout.
    """
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return AxdeviceStepResult(
            step=step, command=cmd, returncode=None, timed_out=True, stdout=partial,
            stderr=f"timed out after {timeout_s:.0f}s",
        )
    return AxdeviceStepResult(
        step=step, command=cmd, returncode=r.returncode, stdout=r.stdout.strip(), stderr=r.stderr.strip(),
    )


@app.get(
    "/api/v1/devices/{device_id}/axdevice", response_model=AxdeviceStatusResponse,
    dependencies=[Depends(require_api_key)],
)
def axdevice_device_status(device_id: int) -> AxdeviceStatusResponse:
    """Report one device's ``axdevice -v`` line and parsed power limit.

    Args:
        device_id (int): Device index.

    Raises:
        HTTPException: 404 if the device is not listed.
    """
    sdk_root = _require_sdk_root()
    axdevice = _axdevice_bin(sdk_root)
    env = os.environ.copy()
    env["AXELERA_FRAMEWORK"] = _axelera_framework_value(sdk_root)
    line = _device_line(axdevice, env, device_id)
    if line is None:
        raise HTTPException(status_code=404, detail=f"device {device_id} not found")
    return AxdeviceStatusResponse(device_id=device_id, device=line, power_limit_w=_parse_power_limit(line))


@app.post(
    "/api/v1/devices/{device_id}/axdevice", response_model=AxdeviceResponse,
    dependencies=[Depends(require_api_key)],
)
def axdevice_device(device_id: int, req: AxdeviceRequest) -> AxdeviceResponse:
    """Refresh a device, reload its firmware and/or set its power limit.

    The optional action runs first. The power limit is set only if every earlier step exited with code 0. Calls are serialized by a non-blocking lock, and the cached device list is cleared afterwards.

    Args:
        device_id (int): Device index.
        req (AxdeviceRequest): What to do; ``confirm`` must be true and ``action`` or ``power_limit_w`` must be given.

    Returns:
        AxdeviceResponse: Per-step results and the device line before and after.

    Raises:
        HTTPException: 400 if ``confirm`` is false, 422 if nothing was requested, 404 if the device is unknown, 409 if axinferencenet processes are running (without ``allow_busy``) or another maintenance call is in progress.
    """
    if not req.confirm:
        raise HTTPException(status_code=400, detail="confirm must be true: this resets or reconfigures real hardware")
    if req.action is None and req.power_limit_w is None:
        raise HTTPException(status_code=422, detail="nothing to do: pass action and/or power_limit_w")

    sdk_root = _require_sdk_root()
    axdevice = _axdevice_bin(sdk_root)
    env = os.environ.copy()
    env["AXELERA_FRAMEWORK"] = _axelera_framework_value(sdk_root)

    known = {d.index for d in _enumerate_devices(sdk_root).devices}
    if device_id not in known:
        raise HTTPException(status_code=404, detail=f"device {device_id} not found (known: {sorted(known)})")

    busy = launch_remote.find_pids_by_name(AXINFERENCENET_BIN_PATH.name)
    if busy and not req.allow_busy:
        raise HTTPException(
            status_code=409,
            detail=f"{len(busy)} {AXINFERENCENET_BIN_PATH.name} process(es) running (pids {busy}); stop them "
                   f"(POST /api/v1/pipelines/cleanup-all) or pass allow_busy=true",
        )

    if not _AXDEVICE_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="another axdevice maintenance call is already running")
    try:
        device_before = _device_line(axdevice, env, device_id)
        steps: list[AxdeviceStepResult] = []
        if req.action is not None:
            steps.append(_run_axdevice_step(
                req.action, [str(axdevice), "-d", str(device_id), _AXDEVICE_ACTION_FLAGS[req.action]],
                env, _AXDEVICE_ACTION_TIMEOUT_S,
            ))
        if req.power_limit_w is not None and all(s.returncode == 0 for s in steps):
            limit = "off" if req.power_limit_w == "off" else f"{req.power_limit_w:g}"
            steps.append(_run_axdevice_step(
                "set_power_limit", [str(axdevice), "-d", str(device_id), "--set-power-limit", limit],
                env, _AXDEVICE_POWER_TIMEOUT_S,
            ))
        device_after = _device_line(axdevice, env, device_id)
        _devices_cache.clear()
    finally:
        _AXDEVICE_LOCK.release()

    return AxdeviceResponse(
        device_id=device_id, ok=all(s.returncode == 0 for s in steps), steps=steps,
        device_before=device_before, device_after=device_after,
        power_limit_w_after=_parse_power_limit(device_after),
    )


# Address of the axsystemserver that axmonitor connects to.
MONITOR_SERVER_ADDRESS = os.environ.get("MONITOR_SERVER_ADDRESS", "127.0.0.1:5555")
_MONITOR_STATS_CACHE_TTL_S = 1.0
_monitor_stats_cache: Optional[tuple[float, "MonitorStatsResponse"]] = None

_MONITOR_DEVICE_HEADER_RE = re.compile(r"^#\s*Device\s+(\d+):\s*(.+)$")
_MONITOR_AI_CORE_HEADER_RE = re.compile(r"^AI-core\s+(\d+):$")
_MONITOR_CORE_UTIL_RE = re.compile(r"(?i)^Core Utilization:\s*([\d.]+)\s*%")
_MONITOR_MVM_PEAK_RE = re.compile(r"(?i)^MVM Peak Utilization:\s*([\d.]+)\s*%")
_MONITOR_MVM_AVG_RE = re.compile(r"(?i)^MVM Average Utilization:\s*([\d.]+)\s*%")
_MONITOR_TOTAL_DDR_RE = re.compile(r"(?i)^Total DDR Size:\s*([\d.]+)\s*MB")
_MONITOR_USED_DDR_RE = re.compile(r"(?i)^Used DDR Size:\s*([\d.]+)\s*MB")
_MONITOR_POWER_LIMIT_RE = re.compile(r"(?i)^Power Limit:\s*([\d.]+)\s*W")
_MONITOR_POWER_SENSOR_HEADER_RE = re.compile(r"^INA\w+ sensor (\d+):$")
_MONITOR_POWER_AVG_RE = re.compile(r"(?i)^Average:\s*([\d.]+)\s*W")


def _resolve_axmonitor_bin() -> Optional[str]:
    """Return the last-sorting ``/opt/axelera/runtime-*/bin/axmonitor``, or None if none is installed."""

    candidates = sorted(glob.glob("/opt/axelera/runtime-*/bin/axmonitor"))
    if not candidates:
        return None
    return candidates[-1]


class MonitorCoreStats(BaseModel):
    """Utilization of one core, in percent.

    Attributes:
        core_utilization_pct (Optional[float]): Core utilization.
        mvm_peak_utilization_pct (Optional[float]): MVM peak utilization.
        mvm_average_utilization_pct (Optional[float]): MVM average utilization.
    """

    core_utilization_pct: Optional[float] = None
    mvm_peak_utilization_pct: Optional[float] = None
    mvm_average_utilization_pct: Optional[float] = None


class MonitorDeviceStats(BaseModel):
    """Parsed AxMonitor statistics for one device.

    Attributes:
        device_name (Optional[str]): Name from the device header line.
        power_limit_w (Optional[float]): Reported power limit in watts.
        power_sensor_0_w (Optional[float]): Average power of INA sensor 0 in watts.
        power_sensor_1_w (Optional[float]): Average power of INA sensor 1 in watts.
        sys_core_utilization_pct (Optional[float]): Sys-core utilization.
        ai_cores (dict[int, MonitorCoreStats]): Per AI-core statistics, keyed by core index.
        ddr_total_mb (Optional[float]): Total DDR size in MB.
        ddr_used_mb (Optional[float]): Used DDR size in MB.
        ddr_utilization_pct (Optional[float]): Used over total DDR, computed here.
    """

    device_name: Optional[str] = None
    power_limit_w: Optional[float] = None
    power_sensor_0_w: Optional[float] = None
    power_sensor_1_w: Optional[float] = None
    sys_core_utilization_pct: Optional[float] = None
    ai_cores: dict[int, MonitorCoreStats] = Field(default_factory=dict)
    ddr_total_mb: Optional[float] = None
    ddr_used_mb: Optional[float] = None
    ddr_utilization_pct: Optional[float] = None


class MonitorStatsResponse(BaseModel):
    """One snapshot of AxMonitor output.

    Attributes:
        devices (dict[int, MonitorDeviceStats]): Statistics keyed by device index.
        raw_output (str): Combined stdout and stderr of the axmonitor run.
    """

    devices: dict[int, MonitorDeviceStats]
    raw_output: str


def _parse_axmonitor_output(raw_output: str) -> dict[int, MonitorDeviceStats]:
    """Parse the text printed by ``axmonitor -c print`` into per-device statistics.

    A ``# Device N: name`` header starts a device; lines before the first header are ignored. Power sensor, Sys-core and AI-core section headers select where the following values are stored, and the DDR utilization percentage is derived at the end.

    Args:
        raw_output (str): Text printed by axmonitor.

    Returns:
        dict[int, MonitorDeviceStats]: Statistics keyed by device index.
    """
    devices: dict[int, MonitorDeviceStats] = {}
    current_device: Optional[MonitorDeviceStats] = None
    current_core: Optional[object] = None
    current_sensor: Optional[int] = None

    for raw_line in raw_output.splitlines():
        line = raw_line.strip()

        if (m := _MONITOR_DEVICE_HEADER_RE.match(line)) is not None:
            current_device = MonitorDeviceStats(device_name=m.group(2).strip())
            devices[int(m.group(1))] = current_device
            current_core = None
            current_sensor = None
            continue

        if current_device is None:
            continue

        if (m := _MONITOR_POWER_SENSOR_HEADER_RE.match(line)) is not None:
            current_sensor = int(m.group(1))
            current_core = None
            continue
        if line.endswith(":") and current_sensor is not None:
            current_sensor = None
        if current_sensor in (0, 1) and (m := _MONITOR_POWER_AVG_RE.match(line)) is not None:
            setattr(current_device, f"power_sensor_{current_sensor}_w", float(m.group(1)))
            continue
        if (m := _MONITOR_POWER_LIMIT_RE.match(line)) is not None:
            current_device.power_limit_w = float(m.group(1))
            continue

        if line == "Sys-core:":
            current_core = "sys"
            continue
        if (m := _MONITOR_AI_CORE_HEADER_RE.match(line)) is not None:
            current_core = int(m.group(1))
            current_device.ai_cores.setdefault(current_core, MonitorCoreStats())
            continue
        if line == "Memory:" or line.startswith("Context "):
            current_core = None
            continue

        if (m := _MONITOR_CORE_UTIL_RE.match(line)) is not None and current_core is not None:
            if current_core == "sys":
                current_device.sys_core_utilization_pct = float(m.group(1))
            else:
                current_device.ai_cores[current_core].core_utilization_pct = float(m.group(1))
            continue
        if (m := _MONITOR_MVM_PEAK_RE.match(line)) is not None and isinstance(current_core, int):
            current_device.ai_cores[current_core].mvm_peak_utilization_pct = float(m.group(1))
            continue
        if (m := _MONITOR_MVM_AVG_RE.match(line)) is not None and isinstance(current_core, int):
            current_device.ai_cores[current_core].mvm_average_utilization_pct = float(m.group(1))
            continue
        if (m := _MONITOR_TOTAL_DDR_RE.match(line)) is not None:
            current_device.ddr_total_mb = float(m.group(1))
            continue
        if (m := _MONITOR_USED_DDR_RE.match(line)) is not None:
            current_device.ddr_used_mb = float(m.group(1))
            continue

    for device in devices.values():
        if device.ddr_total_mb is not None and device.ddr_used_mb is not None and device.ddr_total_mb > 0:
            device.ddr_utilization_pct = device.ddr_used_mb / device.ddr_total_mb * 100.0

    return devices


def _poll_monitor_stats() -> MonitorStatsResponse:
    """Run axmonitor once (5 s timeout) against ``MONITOR_SERVER_ADDRESS`` and parse the result.

    Returns:
        MonitorStatsResponse: Parsed statistics plus the raw output.

    Raises:
        HTTPException: 503 if axmonitor is not installed, times out, or exits non-zero.
    """
    axmonitor_bin = _resolve_axmonitor_bin()
    if axmonitor_bin is None:
        raise HTTPException(
            status_code=503,
            detail="axmonitor is not installed on this host -- run setup.sh with --monitor first",
        )
    lib_dir = os.path.join(os.path.dirname(os.path.dirname(axmonitor_bin)), "lib")
    env = {**os.environ, "LD_LIBRARY_PATH": f"{lib_dir}:{os.environ.get('LD_LIBRARY_PATH', '')}"}

    try:
        result = subprocess.run(
            [axmonitor_bin, "--server-address", MONITOR_SERVER_ADDRESS, "--ui", "console", "-c", "print"],
            capture_output=True, text=True, timeout=5, check=False, env=env,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="axmonitor is not installed on this host -- run setup.sh with --monitor first",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=503, detail="axmonitor timed out -- axsystemserver may not be running")

    raw_output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise HTTPException(
            status_code=503,
            detail=f"axmonitor exited with {result.returncode} (is axsystemserver running?): {raw_output.strip()}",
        )

    devices = _parse_axmonitor_output(result.stdout)
    return MonitorStatsResponse(devices=devices, raw_output=raw_output)


@app.get("/api/v1/monitor/stats", response_model=MonitorStatsResponse, dependencies=[Depends(require_api_key)])
def get_monitor_stats() -> MonitorStatsResponse:
    """Return current AxMonitor statistics for all devices.

    The snapshot is cached for ``_MONITOR_STATS_CACHE_TTL_S`` seconds.

    Raises:
        HTTPException: 503 if axmonitor is unavailable or fails.
    """
    global _monitor_stats_cache
    if _monitor_stats_cache is not None and time.monotonic() - _monitor_stats_cache[0] < _MONITOR_STATS_CACHE_TTL_S:
        return _monitor_stats_cache[1]

    response = _poll_monitor_stats()
    _monitor_stats_cache = (time.monotonic(), response)
    return response


class MonitorRestartResponse(BaseModel):
    """Result of an axsystemserver restart.

    Attributes:
        restarted (bool): True when the restart command succeeded.
        detail (str): Output of the restart command.
    """

    restarted: bool
    detail: str


@app.post(
    "/api/v1/monitor/restart", response_model=MonitorRestartResponse, dependencies=[Depends(require_api_key)],
)
def restart_axsystemserver() -> MonitorRestartResponse:
    """Restart the axsystemserver service with ``service axsystemserver restart`` (30 s timeout) and drop the cached stats.

    Raises:
        HTTPException: 503 if the service command is missing, times out, or exits non-zero.
    """
    global _monitor_stats_cache
    try:
        result = subprocess.run(
            ["service", "axsystemserver", "restart"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="axsystemserver is not installed on this host -- run setup.sh with --monitor first",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=503, detail="service axsystemserver restart timed out")

    raw_output = (result.stdout or "") + (result.stderr or "")
    _monitor_stats_cache = None
    if result.returncode != 0:
        raise HTTPException(
            status_code=503,
            detail=f"service axsystemserver restart exited with {result.returncode}: {raw_output.strip()}",
        )
    return MonitorRestartResponse(restarted=True, detail=raw_output.strip())


class ServerRestartResponse(BaseModel):
    """Acknowledgement of a host server restart request.

    Attributes:
        scheduled (bool): True once the watchdog has been spawned.
        detail (str): Where and when the server will come back.
    """

    scheduled: bool
    detail: str


@app.post(
    "/api/v1/server/restart", response_model=ServerRestartResponse, dependencies=[Depends(require_api_key)],
)
def restart_host_server() -> ServerRestartResponse:
    """Restart this server process.

    Spawns a detached bash watchdog that sleeps 8 s and then starts ``deployment/venv/bin/uvicorn host_server:app`` on ``BIND_HOST``/``BIND_PORT`` (default ``0.0.0.0:8088``), appending output to ``host_server_live.log``. About 1.5 s after the response is returned this process exits with ``os._exit(0)``.

    Returns:
        ServerRestartResponse: Confirmation that the restart is scheduled.

    Raises:
        HTTPException: 503 if the uvicorn binary is missing or the watchdog cannot be spawned.
    """
    uvicorn_bin = DEPLOYMENT_DIR / "venv" / "bin" / "uvicorn"
    if not uvicorn_bin.is_file():
        raise HTTPException(status_code=503, detail=f"uvicorn binary not found at {uvicorn_bin}")

    bind_host = os.environ.get("BIND_HOST", "0.0.0.0")
    bind_port = os.environ.get("BIND_PORT", "8088")
    log_path = DEPLOYMENT_DIR / "host_server_live.log"
    watchdog_cmd = (
        f"sleep 8; exec {uvicorn_bin} host_server:app --host {bind_host} --port {bind_port} "
        f">> {log_path} 2>&1"
    )
    try:
        subprocess.Popen(
            ["bash", "-c", watchdog_cmd],
            cwd=str(DEPLOYMENT_DIR),
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"failed to spawn restart watchdog: {exc}")

    def _delayed_exit() -> None:
        time.sleep(1.5)
        os._exit(0)

    threading.Thread(target=_delayed_exit, daemon=True).start()
    return ServerRestartResponse(
        scheduled=True,
        detail=f"watchdog spawned, will relaunch on {bind_host}:{bind_port} in ~8s; this process exits in ~1.5s",
    )


# Monitor worker limits: devices registered, samples kept per device, minimum and default sampling interval (s), and how often the recorder process is replaced (s).
MONITOR_WORKER_MAX_DEVICES = int(os.environ.get("MONITOR_WORKER_MAX_DEVICES", 30))
MONITOR_WORKER_MAX_SAMPLES = int(os.environ.get("MONITOR_WORKER_MAX_SAMPLES", 50_000))
MONITOR_WORKER_MIN_INTERVAL_S = float(os.environ.get("MONITOR_WORKER_MIN_INTERVAL_S", 1.0))
MONITOR_WORKER_DEFAULT_INTERVAL_S = float(os.environ.get("MONITOR_WORKER_DEFAULT_INTERVAL_S", 1.0))
MONITOR_RECORDER_ROTATE_S = float(os.environ.get("MONITOR_RECORDER_ROTATE_S", 600.0))
_MONITOR_TAILER_POLL_S = 0.2


class _MonitorDeviceBuffer:
    """In-memory ring buffer of AxMonitor samples for one device.

    Attributes:
        interval_s (float): Minimum spacing between stored samples.
        started_at (float): Unix time the worker was registered.
        last_sample_at (Optional[float]): Timestamp of the newest stored sample, in Unix seconds.
        last_error (Optional[str]): Latest recorder problem, cleared when a sample is stored.
        next_keep_ts (float): ``time.monotonic()`` value before which incoming records are dropped.
        buffer_lock (threading.Lock): Guards the fields above and ``history``.
        history (deque[tuple[float, list[dict]]]): ``(timestamp_s, messages)`` pairs, at most ``MONITOR_WORKER_MAX_SAMPLES``.
    """

    def __init__(self, interval_s: float):
        self.interval_s = interval_s
        self.started_at = time.time()
        self.last_sample_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.next_keep_ts = 0.0
        self.buffer_lock = threading.Lock()
        self.history: deque[tuple[float, list[dict]]] = deque(maxlen=MONITOR_WORKER_MAX_SAMPLES)


_monitor_buffers: dict[int, _MonitorDeviceBuffer] = {}
_monitor_buffers_lock = threading.Lock()

_monitor_recorder_proc: Optional[subprocess.Popen] = None
_monitor_recorder_thread: Optional[threading.Thread] = None
_monitor_recorder_stop_event: Optional[threading.Event] = None


def _kill_monitor_recorder_at_exit() -> None:
    """Terminate the axmonitor recorder process, if still running, at interpreter exit."""
    if _monitor_recorder_proc is not None and _monitor_recorder_proc.poll() is None:
        _monitor_recorder_proc.terminate()


atexit.register(_kill_monitor_recorder_at_exit)


def _start_monitor_recorder_process(data_file_base: str) -> subprocess.Popen:
    """Start axmonitor recording to a JSONL file.

    Args:
        data_file_base (str): Output path without extension; axmonitor writes ``<data_file_base>.jsonl``.

    Returns:
        subprocess.Popen: The recorder process. Its stdin is a pipe left open for the caller to close; stdout and stderr are discarded.

    Raises:
        HTTPException: 503 if axmonitor is not installed.
    """
    axmonitor_bin = _resolve_axmonitor_bin()
    if axmonitor_bin is None:
        raise HTTPException(
            status_code=503,
            detail="axmonitor is not installed on this host -- run setup.sh with --monitor first",
        )
    lib_dir = os.path.join(os.path.dirname(os.path.dirname(axmonitor_bin)), "lib")
    env = {**os.environ, "LD_LIBRARY_PATH": f"{lib_dir}:{os.environ.get('LD_LIBRARY_PATH', '')}"}
    return subprocess.Popen(
        [
            axmonitor_bin, "--server-address", MONITOR_SERVER_ADDRESS, "--ui", "console",
            "--record", "--export", "jsonl", "--data-file", data_file_base,
        ],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=env,
    )


def _monitor_tailer_loop(stop_event: threading.Event) -> None:
    """Thread body that feeds the monitor buffers from a recording axmonitor process.

    Repeatedly starts a recorder in a fresh temp directory, tails its JSONL file and dispatches each line, and replaces the recorder every ``MONITOR_RECORDER_ROTATE_S`` seconds. If the recorder exits, ``last_error`` is set on every buffer. The recorder and its temp directory are cleaned up on each pass. Runs until ``stop_event`` is set.

    Args:
        stop_event (threading.Event): Set to ask the loop to finish.
    """
    global _monitor_recorder_proc

    while not stop_event.is_set():
        data_dir = tempfile.mkdtemp(prefix="axmonitor_record_")
        data_file_base = os.path.join(data_dir, "axmonitor")
        jsonl_path = data_file_base + ".jsonl"
        proc = _start_monitor_recorder_process(data_file_base)
        _monitor_recorder_proc = proc
        rotate_at = time.monotonic() + MONITOR_RECORDER_ROTATE_S

        try:
            while not os.path.exists(jsonl_path) and not stop_event.is_set():
                if proc.poll() is not None:
                    with _monitor_buffers_lock:
                        for buf in _monitor_buffers.values():
                            buf.last_error = f"axmonitor recorder exited early (code {proc.returncode})"
                    break
                time.sleep(_MONITOR_TAILER_POLL_S)

            with open(jsonl_path, "r") as f:
                while not stop_event.is_set() and time.monotonic() < rotate_at:
                    line = f.readline()
                    if not line:
                        if proc.poll() is not None:
                            with _monitor_buffers_lock:
                                for buf in _monitor_buffers.values():
                                    buf.last_error = f"axmonitor recorder exited (code {proc.returncode})"
                            break
                        time.sleep(_MONITOR_TAILER_POLL_S)
                        continue
                    _dispatch_monitor_jsonl_line(line)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            proc.stdin.close()
            shutil.rmtree(data_dir, ignore_errors=True)


def _dispatch_monitor_jsonl_line(line: str) -> None:
    """Store one recorded JSONL line in the buffer of its device.

    Lines that are blank, not JSON, lack ``device_stream`` data, or belong to a device with no registered worker are ignored. The record timestamp (milliseconds) becomes seconds, falling back to the current time. A sample is kept only if at least the buffer's ``interval_s`` has passed since the previous kept one.

    Args:
        line (str): One line of the recorder's JSONL output.
    """
    line = line.strip()
    if not line:
        return
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return
    device_stream = record.get("device_stream")
    if device_stream is None:
        return
    device_index = device_stream.get("device_id")
    messages = device_stream.get("messages")
    if device_index is None or messages is None:
        return
    try:
        timestamp_s = int(record["timestamp"]) / 1000.0
    except (KeyError, ValueError, TypeError):
        timestamp_s = time.time()

    with _monitor_buffers_lock:
        buf = _monitor_buffers.get(device_index)
    if buf is None:
        return
    now = time.monotonic()
    with buf.buffer_lock:
        if now < buf.next_keep_ts:
            return
        buf.next_keep_ts = now + buf.interval_s
        buf.last_sample_at = timestamp_s
        buf.last_error = None
        buf.history.append((timestamp_s, messages))


def _ensure_monitor_recorder_running() -> None:
    """Start the tailer thread unless it is already alive.

    Note:
        Called with ``_monitor_buffers_lock`` held.
    """
    global _monitor_recorder_thread, _monitor_recorder_stop_event
    if _monitor_recorder_thread is not None and _monitor_recorder_thread.is_alive():
        return
    _monitor_recorder_stop_event = threading.Event()
    _monitor_recorder_thread = threading.Thread(
        target=_monitor_tailer_loop, args=(_monitor_recorder_stop_event,), daemon=True,
    )
    _monitor_recorder_thread.start()


def _stop_monitor_recorder_if_idle() -> None:
    """Signal the tailer thread to stop when no device buffers remain.

    Note:
        Called with ``_monitor_buffers_lock`` held.
    """
    global _monitor_recorder_thread, _monitor_recorder_stop_event
    if _monitor_buffers:
        return
    if _monitor_recorder_stop_event is not None:
        _monitor_recorder_stop_event.set()
    _monitor_recorder_thread = None
    _monitor_recorder_stop_event = None


class StartMonitorWorkerResponse(BaseModel):
    """Result of registering a monitor worker.

    Attributes:
        already_running (bool): True if the device already had a worker.
        device_index (int): The device.
        interval_s (float): Sampling interval now in effect.
    """

    already_running: bool
    device_index: int
    interval_s: float


@app.post(
    "/api/v1/monitor/workers/{device_index}/start", response_model=StartMonitorWorkerResponse,
    dependencies=[Depends(require_api_key)],
)
def start_monitor_worker(device_index: int, interval_s: float = MONITOR_WORKER_DEFAULT_INTERVAL_S) -> StartMonitorWorkerResponse:
    """Start buffering AxMonitor samples for a device, or update its interval if already started.

    The interval is raised to ``MONITOR_WORKER_MIN_INTERVAL_S`` if smaller. The first worker starts the shared recorder thread.

    Args:
        device_index (int): Device to sample; must be non-negative.
        interval_s (float, optional): Seconds between stored samples. Defaults to ``MONITOR_WORKER_DEFAULT_INTERVAL_S``.

    Returns:
        StartMonitorWorkerResponse: Whether a worker already existed and the interval in effect.

    Raises:
        HTTPException: 400 if the index is negative or ``MONITOR_WORKER_MAX_DEVICES`` workers already exist.
    """
    if device_index < 0:
        raise HTTPException(status_code=400, detail="device_index must be >= 0")
    effective_interval_s = max(interval_s, MONITOR_WORKER_MIN_INTERVAL_S)

    with _monitor_buffers_lock:
        existing = _monitor_buffers.get(device_index)
        if existing is not None:
            existing.interval_s = effective_interval_s
            return StartMonitorWorkerResponse(
                already_running=True, device_index=device_index, interval_s=effective_interval_s,
            )
        if len(_monitor_buffers) >= MONITOR_WORKER_MAX_DEVICES:
            raise HTTPException(
                status_code=400,
                detail=f"device cap reached ({MONITOR_WORKER_MAX_DEVICES} devices already registered)",
            )
        _monitor_buffers[device_index] = _MonitorDeviceBuffer(effective_interval_s)
        _ensure_monitor_recorder_running()

    return StartMonitorWorkerResponse(already_running=False, device_index=device_index, interval_s=effective_interval_s)


@app.post("/api/v1/monitor/workers/{device_index}/stop", dependencies=[Depends(require_api_key)])
def stop_monitor_worker(device_index: int) -> dict:
    """Stop buffering for a device and discard its samples; stops the recorder when no workers remain.

    Args:
        device_index (int): Device whose worker to remove.

    Raises:
        HTTPException: 404 if the device has no worker.
    """
    with _monitor_buffers_lock:
        if device_index not in _monitor_buffers:
            raise HTTPException(status_code=404, detail=f"no active monitor worker for device {device_index}")
        del _monitor_buffers[device_index]
        _stop_monitor_recorder_if_idle()
    return {"stopped": True, "device_index": device_index}


@app.get("/api/v1/monitor/workers", dependencies=[Depends(require_api_key)])
def list_monitor_workers() -> dict:
    """List active monitor workers with their interval, sample count, start time, last sample time and last error."""
    with _monitor_buffers_lock:
        items = list(_monitor_buffers.items())
    workers = []
    for device_index, buf in items:
        with buf.buffer_lock:
            workers.append({
                "device_index": device_index,
                "interval_s": buf.interval_s,
                "sample_count": len(buf.history),
                "max_samples": MONITOR_WORKER_MAX_SAMPLES,
                "started_at": buf.started_at,
                "last_sample_at": buf.last_sample_at,
                "last_error": buf.last_error,
            })
    return {"workers": workers}


@app.get("/api/v1/monitor/workers/{device_index}/samples", dependencies=[Depends(require_api_key)])
def get_monitor_worker_samples(
    device_index: int, n: Optional[int] = None, all: bool = False, index: Optional[int] = None,
) -> dict:
    """Return buffered samples for a device.

    Selection precedence is ``index``, then ``all``, then ``n``; with none of them the newest sample is returned. Lists are in oldest-first order.

    Args:
        device_index (int): Device with an active worker.
        n (Optional[int], optional): Return the most recent ``n`` samples (0 gives none).
        all (bool, optional): Return the whole buffer. Defaults to False.
        index (Optional[int], optional): Return the single sample ``index`` places back from the newest (0 is newest).

    Returns:
        dict: ``device_index``, ``interval_s``, ``total_samples`` and ``samples`` (``timestamp`` and ``messages`` per sample).

    Raises:
        HTTPException: 404 if there is no worker or ``index`` is out of range, 400 if ``index`` or ``n`` is negative.
    """
    with _monitor_buffers_lock:
        buf = _monitor_buffers.get(device_index)
    if buf is None:
        raise HTTPException(status_code=404, detail=f"no active monitor worker for device {device_index}")

    with buf.buffer_lock:
        total_samples = len(buf.history)
        if index is not None:
            if index < 0:
                raise HTTPException(status_code=400, detail="index must be >= 0")
            if index >= total_samples:
                raise HTTPException(
                    status_code=404,
                    detail=f"index {index} out of range -- only {total_samples} sample(s) available",
                )
            picked = [buf.history[total_samples - 1 - index]]
        elif all:
            picked = list(buf.history)
        elif n is not None:
            if n < 0:
                raise HTTPException(status_code=400, detail="n must be >= 0")
            picked = list(buf.history)[-n:] if n > 0 else []
        else:
            picked = [buf.history[-1]] if total_samples > 0 else []
        interval_s = buf.interval_s

    return {
        "device_index": device_index,
        "interval_s": interval_s,
        "total_samples": total_samples,
        "samples": [{"timestamp": ts, "messages": messages} for ts, messages in picked],
    }


# Default model and version for health checks and throughput tests, the default per-device timeout, and how long axrunmodel runs per attempt (seconds).
_HEALTH_CHECK_MODEL = "yolox-m-coco-onnx"
_HEALTH_CHECK_MODEL_VERSION = "1.8.0"
_HEALTH_CHECK_DEFAULT_TIMEOUT_S = 20
_HEALTH_CHECK_RUN_SECONDS = 3
_HEALTH_CHECK_MODEL_DIR = Path(os.environ.get("HEALTH_CHECK_MODEL_DIR", "/tmp/host_server_device_health_check"))

_health_check_lock = threading.Lock()


class DeviceHealth(BaseModel):
    """Health-check outcome for one device.

    Attributes:
        index (int): Device index.
        name (str): Device address.
        cores (int): AIPU cores on the device.
        healthy (bool): True if axrunmodel succeeded.
        attempts (int): Runs made (at most 2; 0 if the model could not be resolved).
        error (Optional[str]): Last failure message, if unhealthy.
    """

    index: int
    name: str
    cores: int
    healthy: bool
    attempts: int
    error: Optional[str] = None


class DevicesHealthResponse(BaseModel):
    """Health-check outcome for a set of devices.

    Attributes:
        devices (list[DeviceHealth]): Per-device results.
        healthy_count (int): Number of healthy devices.
        total_count (int): Number of devices checked.
    """

    devices: list[DeviceHealth]
    healthy_count: int
    total_count: int


class DevicesHealthRequest(BaseModel):
    """Request body for a device health check.

    Attributes:
        device_indices (Optional[list[int]]): Devices to check; None means all.
        per_device_timeout_s (int): Seconds allowed for each axrunmodel run (1 to 600).
        models (Optional[dict[int, str]]): Per-device model override keyed by device index.
    """

    device_indices: Optional[list[int]] = None
    per_device_timeout_s: int = _HEALTH_CHECK_DEFAULT_TIMEOUT_S
    models: Optional[dict[int, str]] = None

    @field_validator("device_indices")
    @classmethod
    def validate_device_indices(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        """Reject negative device indices."""
        if v is not None and any(i < 0 for i in v):
            raise ValueError("device_indices must be non-negative")
        return v

    @field_validator("per_device_timeout_s")
    @classmethod
    def validate_per_device_timeout_s(cls, v: int) -> int:
        """Require a timeout between 1 and 600 seconds."""
        if not 1 <= v <= 600:
            raise ValueError("per_device_timeout_s must be between 1 and 600")
        return v


def _validate_timeout(per_device_timeout_s: int) -> int:
    """Check a query-string timeout is between 1 and 600 seconds.

    Returns:
        int: The timeout, unchanged.

    Raises:
        HTTPException: 400 if it is out of range.
    """
    if not 1 <= per_device_timeout_s <= 600:
        raise HTTPException(status_code=400, detail="per_device_timeout_s must be between 1 and 600")
    return per_device_timeout_s


def _looks_like_local_model_path(model: str) -> bool:
    """Return True if a model value looks like a file path (contains ``/`` or ends in ``.axnet`` or ``.json``) rather than a model-zoo name."""
    return "/" in model or model.endswith(".axnet") or model.endswith(".json")


def _resolve_local_axnet_model_json(sdk_root: Path, axnet_value: str) -> Path:
    """Resolve an ``.axnet`` file to the model JSON named by its ``model=`` line.

    A ``${SDK_ROOT}`` placeholder is expanded and relative paths are taken from the SDK root. A relative model path from the file is tried as absolute (with a leading ``/``) first, then relative to the SDK root.

    Args:
        sdk_root (Path): The SDK root directory.
        axnet_value (str): Path of the ``.axnet`` file.

    Returns:
        Path: The model JSON file.

    Raises:
        HTTPException: 400 if the file is missing, 500 if it has no ``model=`` line or the JSON does not exist.
    """
    axnet_path = Path(axnet_value.replace("${SDK_ROOT}", str(sdk_root)))
    if not axnet_path.is_absolute():
        axnet_path = sdk_root / axnet_path
    if not axnet_path.is_file():
        raise HTTPException(status_code=400, detail=f"model path not found on this host: {axnet_path}")
    match = re.search(r"^model=(.+)$", axnet_path.read_text(), re.MULTILINE)
    if not match:
        raise HTTPException(status_code=500, detail=f"no 'model=' line found in {axnet_path}")
    model_json_path = Path(match.group(1).strip())
    if not model_json_path.is_absolute():
        as_absolute = Path("/") / model_json_path
        model_json_path = as_absolute if as_absolute.is_file() else sdk_root / model_json_path
    if not model_json_path.is_file():
        raise HTTPException(status_code=500, detail=f"resolved model.json not found: {model_json_path}")
    return model_json_path


def _resolve_health_check_artifact(
    axdownloadmodel: Path, model: Optional[str], model_version: Optional[str], sdk_root: Path, env: dict,
) -> tuple[Path, list[str]]:
    """Find the artifact that axrunmodel should run for a health check or throughput test.

    A path-like ``model`` is resolved to a local model JSON with no extra flags. Otherwise ``<name>.axm`` is used from ``_HEALTH_CHECK_MODEL_DIR``, downloaded with ``axdownloadmodel --axm`` if absent. When ``model`` is None the default model and version are used.

    Args:
        axdownloadmodel (Path): The axdownloadmodel binary.
        model (Optional[str]): Model name or local path; None selects the default model.
        model_version (Optional[str]): Version to download; ignored for local paths.
        sdk_root (Path): The SDK root directory.
        env (dict): Environment for the download command.

    Returns:
        tuple[Path, list[str]]: The artifact path and extra axrunmodel flags.

    Raises:
        HTTPException: If a local path cannot be resolved, or 500 if the download fails.
    """
    if model is not None and _looks_like_local_model_path(model):
        return _resolve_local_axnet_model_json(sdk_root, model), []

    name = model or _HEALTH_CHECK_MODEL
    version = model_version or (_HEALTH_CHECK_MODEL_VERSION if model is None else None)
    axm_path = _HEALTH_CHECK_MODEL_DIR / f"{name}.axm"
    if not axm_path.is_file():
        cmd = [str(axdownloadmodel), "--axm", name, "-d", str(_HEALTH_CHECK_MODEL_DIR)]
        if version:
            cmd += ["--version", version]
        download = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
        if download.returncode != 0 or not axm_path.is_file():
            raise HTTPException(status_code=500, detail=f"axdownloadmodel failed for model {name!r}: {download.stderr.strip()}")
    return axm_path, ["--no-double-buffer", "--aipu-cores", str(CORES_PER_DEVICE)]


_health_progress_state_lock = threading.Lock()
_health_progress: dict = {
    "running": False,
    "total": 0,
    "completed": 0,
    "current_indices": [],
    "devices": [],
    "healthy_count": 0,
    "done": False,
    "error": None,
}


def _health_progress_snapshot() -> dict:
    """Return a copy of the async health-check progress state, taken under its lock."""
    with _health_progress_state_lock:
        return {
            **_health_progress,
            "devices": list(_health_progress["devices"]),
            "current_indices": list(_health_progress["current_indices"]),
        }


def _run_devices_health_check(
    sdk_root: Path, device_indices: Optional[list[int]], per_device_timeout_s: int,
    single_index_request: bool = False,
    on_device_start: Optional[Callable[[int], None]] = None,
    on_device_done: Optional[Callable[[DeviceHealth], None]] = None,
    model: Optional[str] = None, model_version: Optional[str] = None,
    models: Optional[dict[int, str]] = None,
) -> DevicesHealthResponse:
    """Run axrunmodel on each selected device in parallel and report which are healthy.

    Each device gets up to two attempts, 3 s apart. Models are resolved once per distinct model value. Only one health check or throughput test may run at a time.

    Args:
        sdk_root (Path): The SDK root directory.
        device_indices (Optional[list[int]]): Devices to check; None means all.
        per_device_timeout_s (int): Seconds allowed for each axrunmodel run.
        single_index_request (bool, optional): Report an unknown index as 404 instead of 400.
        on_device_start (Optional[Callable[[int], None]], optional): Called with the index when a device check begins.
        on_device_done (Optional[Callable[[DeviceHealth], None]], optional): Called with each finished result.
        model (Optional[str], optional): Default model for all devices.
        model_version (Optional[str], optional): Version used with ``model``.
        models (Optional[dict[int, str]], optional): Per-device model override keyed by index.

    Returns:
        DevicesHealthResponse: Results for the checked devices.

    Raises:
        HTTPException: 500 if SDK tools are missing, 404/400 for unknown indices, 409 if another check is running.
    """
    sdk_venv = os.environ.get("SDK_VENV", "venv")
    axdownloadmodel = sdk_root / sdk_venv / "bin" / "axdownloadmodel"
    axrunmodel = sdk_root / sdk_venv / "bin" / "axrunmodel"
    if not axdownloadmodel.is_file():
        raise HTTPException(status_code=500, detail=f"axdownloadmodel not found at {axdownloadmodel}")
    if not axrunmodel.is_file():
        raise HTTPException(status_code=500, detail=f"axrunmodel not found at {axrunmodel}")

    devices_by_index = {d.index: d for d in _enumerate_devices(sdk_root).devices}
    indices = device_indices if device_indices is not None else sorted(devices_by_index)
    unknown = [i for i in indices if i not in devices_by_index]
    if unknown:
        available = sorted(devices_by_index)
        if single_index_request:
            raise HTTPException(
                status_code=404,
                detail=f"device index {unknown[0]} not found; available device indices: {available}",
            )
        raise HTTPException(
            status_code=400,
            detail=f"unknown device index/indices: {unknown}; available device indices: {available}",
        )

    if not _health_check_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="a device health check is already running on this host")
    try:
        env = os.environ.copy()
        env["AXELERA_FRAMEWORK"] = _axelera_framework_value(sdk_root)

        _HEALTH_CHECK_MODEL_DIR.mkdir(parents=True, exist_ok=True)

        _artifact_cache: dict[Optional[str], tuple[Path, list[str]]] = {}
        _artifact_locks: dict[Optional[str], threading.Lock] = {}
        _artifact_locks_guard = threading.Lock()

        def _resolve_for(idx_model: Optional[str]) -> tuple[Path, list[str]]:
            """Resolve and cache the artifact for a model value, serializing concurrent lookups of the same model."""
            with _artifact_locks_guard:
                lock = _artifact_locks.setdefault(idx_model, threading.Lock())
            with lock:
                if idx_model not in _artifact_cache:
                    version = model_version if idx_model is None else None
                    _artifact_cache[idx_model] = _resolve_health_check_artifact(
                        axdownloadmodel, idx_model, version, sdk_root, env,
                    )
                return _artifact_cache[idx_model]

        def _check_one(index: int) -> DeviceHealth:
            """Check a single device, retrying once, and return its result."""
            if on_device_start is not None:
                on_device_start(index)
            device = devices_by_index[index]
            idx_model = (models or {}).get(index, model)
            try:
                artifact_path, extra_axrunmodel_flags = _resolve_for(idx_model)
            except HTTPException as exc:
                result = DeviceHealth(
                    index=index, name=device.name, cores=device.cores,
                    healthy=False, attempts=0, error=str(exc.detail),
                )
                if on_device_done is not None:
                    on_device_done(result)
                return result
            healthy = False
            attempts = 0
            error: Optional[str] = None
            for attempt in range(2):
                attempts += 1
                try:
                    run = subprocess.run(
                        [str(axrunmodel), f"-d{index}", *extra_axrunmodel_flags,
                         "--seconds", str(_HEALTH_CHECK_RUN_SECONDS), str(artifact_path)],
                        capture_output=True, text=True, env=env, cwd=str(_HEALTH_CHECK_MODEL_DIR),
                        timeout=per_device_timeout_s, check=False,
                    )
                except subprocess.TimeoutExpired:
                    error = f"axrunmodel timed out after {per_device_timeout_s}s"
                else:
                    if run.returncode == 0:
                        healthy = True
                        error = None
                        break
                    error = (run.stderr.strip() or run.stdout.strip())[-2000:]
                if attempt == 0:
                    time.sleep(3)
            result = DeviceHealth(
                index=index, name=device.name, cores=device.cores,
                healthy=healthy, attempts=attempts, error=error,
            )
            if on_device_done is not None:
                on_device_done(result)
            return result

        if indices:
            with ThreadPoolExecutor(max_workers=len(indices)) as pool:
                results = list(pool.map(_check_one, indices))
        else:
            results = []

        return DevicesHealthResponse(
            devices=results,
            healthy_count=sum(1 for r in results if r.healthy),
            total_count=len(results),
        )
    finally:
        _health_check_lock.release()


def _run_devices_health_check_background(
    sdk_root: Path, per_device_timeout_s: int,
    model: Optional[str] = None, model_version: Optional[str] = None,
) -> None:
    """Thread body for the asynchronous all-device health check; records progress in ``_health_progress``.

    Args:
        sdk_root (Path): The SDK root directory.
        per_device_timeout_s (int): Seconds allowed for each axrunmodel run.
        model (Optional[str], optional): Model name or path; None selects the default.
        model_version (Optional[str], optional): Version used with ``model``.
    """
    def on_device_start(index: int) -> None:
        """Mark a device as currently being checked."""
        with _health_progress_state_lock:
            _health_progress["current_indices"].append(index)

    def on_device_done(result: DeviceHealth) -> None:
        """Record a finished device result and update the counters."""
        with _health_progress_state_lock:
            if result.index in _health_progress["current_indices"]:
                _health_progress["current_indices"].remove(result.index)
            _health_progress["devices"].append(result.model_dump())
            _health_progress["completed"] += 1
            if result.healthy:
                _health_progress["healthy_count"] += 1

    try:
        _run_devices_health_check(
            sdk_root, None, per_device_timeout_s,
            on_device_start=on_device_start, on_device_done=on_device_done,
            model=model, model_version=model_version,
        )
    except HTTPException as exc:
        with _health_progress_state_lock:
            _health_progress["error"] = str(exc.detail)
    finally:
        with _health_progress_state_lock:
            _health_progress["running"] = False
            _health_progress["done"] = True
            _health_progress["current_indices"] = []


@app.post("/api/v1/devices/health", response_model=DevicesHealthResponse, dependencies=[Depends(require_api_key)])
def check_devices_health(req: DevicesHealthRequest = DevicesHealthRequest()) -> DevicesHealthResponse:
    """Run a health check on the devices listed in the request (all devices if none listed) and wait for the result."""
    sdk_root = _require_sdk_root()
    return _run_devices_health_check(
        sdk_root, req.device_indices, req.per_device_timeout_s, models=req.models,
    )


@app.post("/api/v1/devices/health/all", response_model=DevicesHealthResponse, dependencies=[Depends(require_api_key)])
def check_all_devices_health(
    per_device_timeout_s: int = _HEALTH_CHECK_DEFAULT_TIMEOUT_S,
    model: Optional[str] = None, model_version: Optional[str] = None,
) -> DevicesHealthResponse:
    """Run a health check on every device and wait for the result.

    Args:
        per_device_timeout_s (int, optional): Seconds allowed per run (1 to 600).
        model (Optional[str], optional): Model name or local path; None selects the default.
        model_version (Optional[str], optional): Version used with ``model``.
    """
    sdk_root = _require_sdk_root()
    return _run_devices_health_check(
        sdk_root, None, _validate_timeout(per_device_timeout_s), model=model, model_version=model_version,
    )


@app.post(
    "/api/v1/devices/health/{index}", response_model=DevicesHealthResponse, dependencies=[Depends(require_api_key)],
)
def check_one_device_health(
    index: int, per_device_timeout_s: int = _HEALTH_CHECK_DEFAULT_TIMEOUT_S,
    model: Optional[str] = None, model_version: Optional[str] = None,
) -> DevicesHealthResponse:
    """Run a health check on one device and wait for the result.

    Args:
        index (int): Device index.
        per_device_timeout_s (int, optional): Seconds allowed for the run (1 to 600).
        model (Optional[str], optional): Model name or local path; None selects the default.
        model_version (Optional[str], optional): Version used with ``model``.

    Raises:
        HTTPException: 400 if the index is negative, 404 if the device is not found.
    """
    if index < 0:
        raise HTTPException(status_code=400, detail="device index must be non-negative")
    sdk_root = _require_sdk_root()
    return _run_devices_health_check(
        sdk_root, [index], _validate_timeout(per_device_timeout_s), single_index_request=True,
        model=model, model_version=model_version,
    )


class StartDevicesHealthResponse(BaseModel):
    """Result of starting the asynchronous health check.

    Attributes:
        already_running (bool): True if a run was already in progress.
        total (int): Number of devices in the run.
    """

    already_running: bool
    total: int


@app.post(
    "/api/v1/devices/health/all/start", response_model=StartDevicesHealthResponse,
    dependencies=[Depends(require_api_key)],
)
def start_all_devices_health(
    per_device_timeout_s: int = _HEALTH_CHECK_DEFAULT_TIMEOUT_S,
    model: Optional[str] = None, model_version: Optional[str] = None,
) -> StartDevicesHealthResponse:
    """Start a background health check of all devices and return immediately.

    Progress is read from ``/api/v1/devices/health/status``. If a run is already in progress nothing new is started.

    Args:
        per_device_timeout_s (int, optional): Seconds allowed per run (1 to 600).
        model (Optional[str], optional): Model name or local path; None selects the default.
        model_version (Optional[str], optional): Version used with ``model``.
    """

    sdk_root = _require_sdk_root()
    per_device_timeout_s = _validate_timeout(per_device_timeout_s)
    with _health_progress_state_lock:
        if _health_progress["running"]:
            return StartDevicesHealthResponse(already_running=True, total=_health_progress["total"])
        total = len(_enumerate_devices(sdk_root).devices)
        _health_progress.update({
            "running": True, "total": total, "completed": 0, "current_indices": [],
            "devices": [], "healthy_count": 0, "done": False, "error": None,
        })
    threading.Thread(
        target=_run_devices_health_check_background,
        args=(sdk_root, per_device_timeout_s, model, model_version), daemon=True,
    ).start()
    return StartDevicesHealthResponse(already_running=False, total=total)


@app.get("/api/v1/devices/health/status", dependencies=[Depends(require_api_key)])
def get_devices_health_status() -> dict:
    """Return progress of the background health check (running, total, completed, in-flight indices, finished device results, healthy count, done, error)."""
    return _health_progress_snapshot()


_THROUGHPUT_MIN_SECONDS = 1
_THROUGHPUT_MAX_SECONDS = 3600
# Matches the frame rate printed by axrunmodel; all matches in the output are summed.
_THROUGHPUT_FPS_RE = re.compile(r"system:([0-9.]+)")


class DeviceThroughput(BaseModel):
    """Throughput measured on one device.

    Attributes:
        index (int): Device index.
        fps (float): Sum of the ``system:`` frame rates printed by axrunmodel; 0.0 on error.
        error (Optional[str]): Failure message, if the run failed.
    """

    index: int
    fps: float
    error: Optional[str] = None


class DevicesThroughputResponse(BaseModel):
    """Throughput results for a set of devices.

    Attributes:
        devices (list[DeviceThroughput]): Per-device results.
        aggregate_fps (float): Sum of ``fps`` over devices that succeeded.
        succeeded_count (int): Devices without an error.
        total_count (int): Devices measured.
    """

    devices: list[DeviceThroughput]
    aggregate_fps: float
    succeeded_count: int
    total_count: int


class DevicesThroughputRequest(BaseModel):
    """Request body for a throughput test.

    Attributes:
        device_indices (list[int]): Devices to run on, non-empty and non-negative.
        seconds (int): Run length per device (1 to 3600).
        model (Optional[str]): Model name or local path; None selects the default.
        model_version (Optional[str]): Version used with ``model``.
    """

    device_indices: list[int]
    seconds: int = 30
    model: Optional[str] = None
    model_version: Optional[str] = None

    @field_validator("device_indices")
    @classmethod
    def validate_device_indices(cls, v: list[int]) -> list[int]:
        """Require a non-empty list of non-negative device indices."""
        if not v:
            raise ValueError("device_indices must not be empty")
        if any(i < 0 for i in v):
            raise ValueError("device_indices must be non-negative")
        return v

    @field_validator("seconds")
    @classmethod
    def validate_seconds(cls, v: int) -> int:
        """Require a duration within the allowed throughput range."""
        if not _THROUGHPUT_MIN_SECONDS <= v <= _THROUGHPUT_MAX_SECONDS:
            raise ValueError(f"seconds must be between {_THROUGHPUT_MIN_SECONDS} and {_THROUGHPUT_MAX_SECONDS}")
        return v


def _run_devices_throughput(
    sdk_root: Path, device_indices: list[int], seconds: int,
    model: Optional[str], model_version: Optional[str],
) -> DevicesThroughputResponse:
    """Run axrunmodel for a fixed duration on several devices in parallel and sum the frame rates.

    Shares ``_health_check_lock`` with the health checks, so only one of them runs at a time. Each run has a timeout of ``seconds`` plus 60 s.

    Args:
        sdk_root (Path): The SDK root directory.
        device_indices (list[int]): Devices to run on.
        seconds (int): Run length per device.
        model (Optional[str]): Model name or local path; None selects the default.
        model_version (Optional[str]): Version used with ``model``.

    Returns:
        DevicesThroughputResponse: Per-device and aggregate results.

    Raises:
        HTTPException: 500 if SDK tools are missing, 400 for unknown indices, 409 if a health check or throughput test is running.
    """
    sdk_venv = os.environ.get("SDK_VENV", "venv")
    axdownloadmodel = sdk_root / sdk_venv / "bin" / "axdownloadmodel"
    axrunmodel = sdk_root / sdk_venv / "bin" / "axrunmodel"
    if not axdownloadmodel.is_file():
        raise HTTPException(status_code=500, detail=f"axdownloadmodel not found at {axdownloadmodel}")
    if not axrunmodel.is_file():
        raise HTTPException(status_code=500, detail=f"axrunmodel not found at {axrunmodel}")

    devices_by_index = {d.index: d for d in _enumerate_devices(sdk_root).devices}
    unknown = [i for i in device_indices if i not in devices_by_index]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"unknown device index/indices: {unknown}; available device indices: {sorted(devices_by_index)}",
        )

    if not _health_check_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409, detail="a device health check or throughput test is already running on this host",
        )
    try:
        env = os.environ.copy()
        env["AXELERA_FRAMEWORK"] = _axelera_framework_value(sdk_root)
        _HEALTH_CHECK_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        artifact_path, extra_flags = _resolve_health_check_artifact(
            axdownloadmodel, model, model_version, sdk_root, env,
        )

        timeout_s = seconds + 60

        def _run_one(index: int) -> DeviceThroughput:
            try:
                run = subprocess.run(
                    [str(axrunmodel), f"-d{index}", *extra_flags,
                     "--seconds", str(seconds), str(artifact_path)],
                    capture_output=True, text=True, env=env, cwd=str(_HEALTH_CHECK_MODEL_DIR),
                    timeout=timeout_s, check=False,
                )
            except subprocess.TimeoutExpired:
                return DeviceThroughput(index=index, fps=0.0, error=f"axrunmodel timed out after {timeout_s}s")
            if run.returncode != 0:
                error = (run.stderr.strip() or run.stdout.strip())[-2000:]
                return DeviceThroughput(index=index, fps=0.0, error=error)
            fps = sum(float(m) for m in _THROUGHPUT_FPS_RE.findall(run.stdout))
            return DeviceThroughput(index=index, fps=fps)

        with ThreadPoolExecutor(max_workers=len(device_indices)) as pool:
            results = list(pool.map(_run_one, device_indices))

        return DevicesThroughputResponse(
            devices=results,
            aggregate_fps=sum(r.fps for r in results if r.error is None),
            succeeded_count=sum(1 for r in results if r.error is None),
            total_count=len(results),
        )
    finally:
        _health_check_lock.release()


@app.post(
    "/api/v1/devices/throughput", response_model=DevicesThroughputResponse,
    dependencies=[Depends(require_api_key)],
)
def run_devices_throughput(req: DevicesThroughputRequest) -> DevicesThroughputResponse:
    """Measure frame throughput on the requested devices and wait for the result."""
    sdk_root = _require_sdk_root()
    return _run_devices_throughput(sdk_root, req.device_indices, req.seconds, req.model, req.model_version)


_SYSFS_NODE_ROOT = Path("/sys/devices/system/node")
_METIS_ADDR_RE = re.compile(r"^metis-\d+:([0-9a-fA-F]+):\d+$")


class NumaDevicePlan(BaseModel):
    """CPU assignment for one device.

    Attributes:
        index (int): Device index.
        metis_addr (str): Device address as printed by axdevice.
        numa_node (int): NUMA node the device is attached to.
        cpus (list[int]): Logical CPUs reserved for this device.
    """

    index: int
    metis_addr: str
    numa_node: int
    cpus: list[int]


class NumaPlanResponse(BaseModel):
    """CPU pinning plan for a set of devices.

    Attributes:
        numa_available (bool): True when the host has at least two NUMA nodes.
        cores_per_device (int): CPUs assigned to each device.
        plan (list[NumaDevicePlan]): One entry per requested device, in request order.
    """

    numa_available: bool
    cores_per_device: int
    plan: list[NumaDevicePlan]


def _numa_node_count() -> int:
    """Return the number of NUMA nodes under ``/sys/devices/system/node`` (0 if the directory is absent)."""
    if not _SYSFS_NODE_ROOT.is_dir():
        return 0
    return len([p for p in _SYSFS_NODE_ROOT.glob("node[0-9]*") if p.is_dir()])


def _cpulist_to_ids(cpulist: str) -> list[int]:
    """Expand a kernel CPU list string into sorted CPU ids.

    Args:
        cpulist (str): Text such as ``0-3,8``.

    Returns:
        list[int]: The listed CPU ids.
    """
    ids: list[int] = []
    for part in cpulist.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-")
            ids.extend(range(int(lo), int(hi) + 1))
        else:
            ids.append(int(part))
    return sorted(ids)


def _all_online_cpu_ids() -> list[int]:
    """Return the online CPU ids from sysfs, or ``range(os.cpu_count())`` if sysfs cannot be read."""
    online_path = Path("/sys/devices/system/cpu/online")
    try:
        return _cpulist_to_ids(online_path.read_text().strip())
    except OSError:
        return list(range(os.cpu_count() or 0))


@app.get("/api/v1/devices/numa_plan", response_model=NumaPlanResponse, dependencies=[Depends(require_api_key)])
def get_devices_numa_plan(indices: str, cores_per_device: int = CORES_PER_DEVICE) -> NumaPlanResponse:
    """Plan CPU pinning for devices so each gets its own block of CPUs on its NUMA node.

    On a host with two or more NUMA nodes the node of each device comes from its PCI ``numa_node`` in sysfs, assuming PCI domain 0000. Otherwise all devices use node 0 and the online CPUs. Within a node, devices take consecutive blocks of ``cores_per_device`` CPUs in request order.

    Args:
        indices (str): Comma-separated device indices.
        cores_per_device (int, optional): CPUs per device. Defaults to ``CORES_PER_DEVICE``.

    Returns:
        NumaPlanResponse: The plan.

    Raises:
        HTTPException: 400 for a malformed or empty list, 404 for unknown devices, 500 if the PCI address or sysfs files cannot be read, 409 if a node has too few CPUs.
    """

    sdk_root = _require_sdk_root()
    try:
        wanted = [int(x) for x in indices.split(",") if x.strip() != ""]
    except ValueError:
        raise HTTPException(status_code=400, detail="indices must be a comma-separated list of integers")
    if not wanted:
        raise HTTPException(status_code=400, detail="indices must not be empty")

    devices_by_index = {d.index: d for d in _enumerate_devices(sdk_root).devices}
    missing = [i for i in wanted if i not in devices_by_index]
    if missing:
        raise HTTPException(status_code=404, detail=f"device index(es) {missing} not found")

    multi_numa = _numa_node_count() >= 2
    node_of: dict[int, int] = {}
    if multi_numa:
        for idx in wanted:
            addr = devices_by_index[idx].name
            m = _METIS_ADDR_RE.match(addr)
            if not m:
                raise HTTPException(status_code=500, detail=f"could not parse PCI bus from device address {addr!r}")
            numa_path = Path(f"/sys/bus/pci/devices/0000:{m.group(1)}:00.0/numa_node")
            try:
                node_of[idx] = int(numa_path.read_text().strip())
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f"could not read {numa_path} for device {idx}: {exc}")
    else:
        node_of = {idx: 0 for idx in wanted}

    node_cpu_ids: dict[int, list[int]] = {}
    per_node_pos: dict[int, int] = {}
    plan: list[NumaDevicePlan] = []
    for idx in wanted:
        node = node_of[idx]
        pos = per_node_pos.get(node, 0)
        per_node_pos[node] = pos + 1
        if node not in node_cpu_ids:
            if multi_numa:
                cpulist_path = _SYSFS_NODE_ROOT / f"node{node}" / "cpulist"
                try:
                    node_cpu_ids[node] = _cpulist_to_ids(cpulist_path.read_text().strip())
                except OSError as exc:
                    raise HTTPException(status_code=500, detail=f"could not read {cpulist_path}: {exc}")
            else:
                node_cpu_ids[node] = _all_online_cpu_ids()
        cpu_ids = node_cpu_ids[node]
        slice_lo, slice_hi = pos * cores_per_device, (pos + 1) * cores_per_device
        cpus = cpu_ids[slice_lo:slice_hi]
        if len(cpus) < cores_per_device:
            raise HTTPException(
                status_code=409,
                detail=(f"device {idx} (node{node}, position {pos}) needs {cores_per_device} cpus starting "
                        f"at slot {slice_lo}, but only {len(cpu_ids)} logical cpus are available in its pool -- "
                        f"too many devices for this host at {cores_per_device} cores/device"),
            )
        plan.append(NumaDevicePlan(
            index=idx, metis_addr=devices_by_index[idx].name, numa_node=node, cpus=cpus,
        ))

    return NumaPlanResponse(numa_available=multi_numa, cores_per_device=cores_per_device, plan=plan)


class NumaNodeCpuInfo(BaseModel):
    """CPU count for one NUMA node.

    Attributes:
        node (int): NUMA node number.
        total_cpus (int): Logical CPUs on the node.
        pinning_capacity (int): CPUs available for pinning; currently equal to ``total_cpus``.
    """

    node: int
    total_cpus: int
    pinning_capacity: int


class CpuTopologyResponse(BaseModel):
    """CPU topology of the host.

    Attributes:
        numa_available (bool): True when the host has at least two NUMA nodes.
        total_cpus (int): Logical CPUs on the host.
        nodes (list[NumaNodeCpuInfo]): Per-node counts; empty without NUMA.
    """

    numa_available: bool
    total_cpus: int
    nodes: list[NumaNodeCpuInfo]


@app.get("/api/v1/devices/cpu_topology", response_model=CpuTopologyResponse, dependencies=[Depends(require_api_key)])
def get_cpu_topology() -> CpuTopologyResponse:
    """Report the host's NUMA nodes and CPU counts (without per-node entries when there are fewer than two nodes)."""
    if _numa_node_count() < 2:
        return CpuTopologyResponse(numa_available=False, total_cpus=os.cpu_count() or 0, nodes=[])
    nodes: list[NumaNodeCpuInfo] = []
    for node_dir in sorted(_SYSFS_NODE_ROOT.glob("node[0-9]*"), key=lambda p: int(p.name[4:])):
        node = int(node_dir.name[4:])
        try:
            cpulist = (node_dir / "cpulist").read_text().strip()
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"could not read {node_dir / 'cpulist'}: {exc}")
        total_cpus = len(_cpulist_to_ids(cpulist))
        nodes.append(NumaNodeCpuInfo(node=node, total_cpus=total_cpus, pinning_capacity=total_cpus))
    return CpuTopologyResponse(numa_available=True, total_cpus=sum(n.total_cpus for n in nodes), nodes=nodes)


class PrebuiltModelsResponse(BaseModel):
    """Models available for download.

    Attributes:
        models (list[str]): Non-empty lines printed by ``axdownloadmodel --list``.
    """

    models: list[str]


# Cache of the prebuilt model list keyed by SDK root: (time.monotonic() stamp, response).
_PREBUILT_MODELS_CACHE_TTL_S = 600.0
_prebuilt_models_cache: dict[str, tuple[float, "PrebuiltModelsResponse"]] = {}


@app.get("/api/v1/prebuilt-models", response_model=PrebuiltModelsResponse, dependencies=[Depends(require_api_key)])
def list_prebuilt_models() -> PrebuiltModelsResponse:
    """List the models that axdownloadmodel can fetch.

    The result is cached per SDK root for ``_PREBUILT_MODELS_CACHE_TTL_S`` seconds.

    Raises:
        HTTPException: 500 if axdownloadmodel is missing or fails.
    """
    sdk_root = _require_sdk_root()

    cached = _prebuilt_models_cache.get(str(sdk_root))
    if cached is not None and time.monotonic() - cached[0] < _PREBUILT_MODELS_CACHE_TTL_S:
        return cached[1]

    sdk_venv = os.environ.get("SDK_VENV", "venv")
    axdownloadmodel = sdk_root / sdk_venv / "bin" / "axdownloadmodel"
    if not axdownloadmodel.is_file():
        raise HTTPException(status_code=500, detail=f"axdownloadmodel not found at {axdownloadmodel}")

    env = os.environ.copy()
    env["AXELERA_FRAMEWORK"] = _axelera_framework_value(sdk_root)
    result = subprocess.run(
        [str(axdownloadmodel), "--list"], capture_output=True, text=True, env=env,
        cwd=str(sdk_root), check=False,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"axdownloadmodel --list failed: {result.stderr.strip()}")

    models = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    response = PrebuiltModelsResponse(models=models)
    _prebuilt_models_cache[str(sdk_root)] = (time.monotonic(), response)
    return response


_model_download_lock = threading.Lock()


class PrebuiltModelDownloadRequest(BaseModel):
    """Request to download and provision a prebuilt model.

    Attributes:
        name (str): Model name (1 to 100 characters of letters, digits, ``_``, ``.``, ``-``).
        version (Optional[str]): Model version passed to axdownloadmodel.
        opencl (bool): Generate the ``.axnet`` with OpenCL enabled.
        device (Optional[int]): Device used for provisioning; None picks the lowest index.
        aipu_cores (int): AIPU cores to compile for (1 to ``CORES_PER_DEVICE``).
        force (bool): Regenerate the ``.axnet`` even if it exists.
        artifacts_only (bool): Only download the model artifacts; skip ``.axnet`` generation.
    """

    name: str
    version: Optional[str] = None
    opencl: bool = True
    device: Optional[int] = None
    aipu_cores: int = CORES_PER_DEVICE
    force: bool = False
    artifacts_only: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Require a safe model name."""
        if not _SAFE_MODEL_NAME_RE.match(v):
            raise ValueError("name must be 1-100 chars of letters, digits, '_', '.', or '-'")
        return v

    @field_validator("aipu_cores")
    @classmethod
    def validate_aipu_cores(cls, v: int) -> int:
        """Require a core count between 1 and ``CORES_PER_DEVICE``."""
        if not 1 <= v <= CORES_PER_DEVICE:
            raise ValueError(f"aipu_cores must be between 1 and {CORES_PER_DEVICE}")
        return v


class PrebuiltModelDownloadResponse(BaseModel):
    """Result of a model download and provisioning request.

    Attributes:
        axnet_path (Optional[str]): ``${SDK_ROOT}``-prefixed path of the ``.axnet``; None in ``artifacts_only`` mode.
        already_present (bool): Whether the ``.axnet`` existed before this call.
        regenerated (bool): Whether the ``.axnet`` was generated by this call.
    """

    axnet_path: Optional[str] = None
    already_present: bool
    regenerated: bool


def _pick_provisioning_device(sdk_root: Path, requested: Optional[int]) -> int:
    """Choose the device used for model provisioning.

    Args:
        sdk_root (Path): The SDK root directory.
        requested (Optional[int]): Requested index, or None for the lowest available.

    Returns:
        int: The device index.

    Raises:
        HTTPException: 500 if no devices exist, 404 if the requested index is unknown.
    """
    devices_by_index = {d.index: d for d in _enumerate_devices(sdk_root).devices}
    if not devices_by_index:
        raise HTTPException(status_code=500, detail="no devices found on this host (axdevice reported none)")
    if requested is None:
        return sorted(devices_by_index)[0]
    if requested not in devices_by_index:
        raise HTTPException(
            status_code=404,
            detail=f"device index {requested} not found; available device indices: {sorted(devices_by_index)}",
        )
    return requested


@app.post(
    "/api/v1/prebuilt-models/download", response_model=PrebuiltModelDownloadResponse,
    dependencies=[Depends(require_api_key)],
)
def download_prebuilt_model(req: PrebuiltModelDownloadRequest) -> PrebuiltModelDownloadResponse:
    """Download a prebuilt model and generate its ``.axnet`` file under ``SDK_ROOT/build/<name>/``.

    With ``artifacts_only`` the model is downloaded and the call returns. Otherwise an existing ``.axnet`` is returned as is unless ``force`` is set. If the ``.axnet`` is missing the model is downloaded first. The ``.axnet`` is then regenerated with ``axnet._regenerate_one`` on a device and checked with ``axnet.smoke_test``; on failure the ``.axnet`` is deleted.

    Args:
        req (PrebuiltModelDownloadRequest): What to download and how to provision it.

    Returns:
        PrebuiltModelDownloadResponse: Where the ``.axnet`` is and whether it was generated.

    Raises:
        HTTPException: 500 if tools or test media are missing or a download, regeneration or smoke test fails, 404 for an unknown device, 409 if another download/provision or a health check is running.
    """

    sdk_root = _require_sdk_root()
    name = req.name
    axnet_path = sdk_root / "build" / name / f"{name}.axnet"

    if req.artifacts_only:
        sdk_venv = os.environ.get("SDK_VENV", "venv")
        axdownloadmodel = sdk_root / sdk_venv / "bin" / "axdownloadmodel"
        if not axdownloadmodel.is_file():
            raise HTTPException(status_code=500, detail=f"axdownloadmodel not found at {axdownloadmodel}")
        if not _model_download_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="a model download/provision is already running on this host")
        try:
            env = os.environ.copy()
            env["AXELERA_FRAMEWORK"] = _axelera_framework_value(sdk_root)
            cmd = [str(axdownloadmodel), name]
            if req.version:
                cmd += ["--version", req.version]
            result = subprocess.run(
                cmd, capture_output=True, text=True, env=env, cwd=str(sdk_root), check=False,
            )
            if result.returncode != 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"axdownloadmodel failed for model {name!r}: "
                           f"{(result.stderr.strip() or result.stdout.strip())[-2000:]}",
                )
        finally:
            _model_download_lock.release()
        return PrebuiltModelDownloadResponse(
            axnet_path=None, already_present=axnet_path.is_file(), regenerated=False,
        )

    opencl_flag = "--enable-opencl" if req.opencl else "--disable-opencl"

    if axnet_path.is_file() and not req.force:
        return PrebuiltModelDownloadResponse(
            axnet_path=f"${{SDK_ROOT}}/build/{name}/{name}.axnet", already_present=True, regenerated=False,
        )

    sdk_venv = os.environ.get("SDK_VENV", "venv")
    axdownloadmodel = sdk_root / sdk_venv / "bin" / "axdownloadmodel"
    if not axdownloadmodel.is_file():
        raise HTTPException(status_code=500, detail=f"axdownloadmodel not found at {axdownloadmodel}")
    if not _MODEL_PROVISION_MEDIA.is_file():
        raise HTTPException(status_code=500, detail=f"test media not found at {_MODEL_PROVISION_MEDIA}")

    device_index = _pick_provisioning_device(sdk_root, req.device)
    was_present = axnet_path.is_file()

    if not _model_download_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="a model download/provision is already running on this host")
    try:
        if not was_present:
            env = os.environ.copy()
            env["AXELERA_FRAMEWORK"] = _axelera_framework_value(sdk_root)
            cmd = [str(axdownloadmodel), name]
            if req.version:
                cmd += ["--version", req.version]
            result = subprocess.run(
                cmd, capture_output=True, text=True, env=env, cwd=str(sdk_root), check=False,
            )
            if result.returncode != 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"axdownloadmodel failed for model {name!r}: "
                           f"{(result.stderr.strip() or result.stdout.strip())[-2000:]}",
                )

        if not _health_check_lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409,
                detail="a device health check is currently using this host's devices -- try again shortly",
            )
        try:
            _axnet._regenerate_one(
                str(sdk_root), sdk_venv, opencl_flag, str(axnet_path),
                str(_MODEL_PROVISION_MEDIA), _MODEL_PROVISION_FRAMES, req.aipu_cores, device_index,
            )
            expect_async_mode = _axnet._ASYNC_EXECUTOR_FLAG_SUPPORTED.get(
                (str(sdk_root), sdk_venv), True
            )
            _axnet.smoke_test(str(axnet_path), opencl_enabled=req.opencl,
                               expect_async_mode=expect_async_mode)
        except (subprocess.CalledProcessError, RuntimeError, AssertionError) as exc:
            Path(axnet_path).unlink(missing_ok=True)
            output_tail = ""
            if isinstance(exc, subprocess.CalledProcessError):
                output_tail = (exc.stderr or exc.output or "").strip()[-2000:]
            raise HTTPException(
                status_code=500,
                detail=f"axnet.py regenerate/smoke-test failed for model {name!r} on device "
                       f"{device_index}: {exc}" + (f" -- {output_tail}" if output_tail else ""),
            )
        finally:
            _health_check_lock.release()
    finally:
        _model_download_lock.release()

    if not axnet_path.is_file():
        raise HTTPException(status_code=500, detail=f".axnet still missing after provisioning: {axnet_path}")
    return PrebuiltModelDownloadResponse(
        axnet_path=f"${{SDK_ROOT}}/build/{name}/{name}.axnet", already_present=was_present, regenerated=True,
    )


class AxnetMetaKeyPatchRequest(BaseModel):
    """Request to rewrite the meta key of a provisioned model.

    Attributes:
        name (str): Model name.
        meta_key (str): New meta key.
    """

    name: str
    meta_key: str


class AxnetMetaKeyPatchResponse(BaseModel):
    """Result of a meta-key patch.

    Attributes:
        axnet_path (str): ``${SDK_ROOT}``-prefixed path of the ``.axnet``.
        patched (bool): True if the file was modified.
    """

    axnet_path: str
    patched: bool


@app.post(
    "/api/v1/prebuilt-models/patch-meta-key", response_model=AxnetMetaKeyPatchResponse,
    dependencies=[Depends(require_api_key)],
)
def patch_axnet_meta_key(req: AxnetMetaKeyPatchRequest) -> AxnetMetaKeyPatchResponse:
    """Rewrite the ``meta_key`` values in a provisioned model's ``.axnet`` file.

    Delegates to ``axnet._patch_meta_key_if_requested``, which edits the file in place.

    Args:
        req (AxnetMetaKeyPatchRequest): Model name and new meta key.

    Raises:
        HTTPException: 404 if the model's ``.axnet`` does not exist.
    """

    sdk_root = _require_sdk_root()
    name = req.name
    axnet_path = sdk_root / "build" / name / f"{name}.axnet"
    if not axnet_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f".axnet for model {name!r} not found at {axnet_path} -- provision it first via "
                   f"/api/v1/prebuilt-models/download",
        )
    patched = _axnet._patch_meta_key_if_requested(str(axnet_path), req.meta_key)
    return AxnetMetaKeyPatchResponse(
        axnet_path=f"${{SDK_ROOT}}/build/{name}/{name}.axnet", patched=patched,
    )


class PipelineSpecUploadRequest(BaseModel):
    """Request to store a pipeline spec.

    Attributes:
        pipeline_id (str): Pipeline identifier (1 to 100 characters of letters, digits, ``_``, ``-``).
        filename (str): Bare ``*.json`` file name.
        spec_content (str): JSON text of the spec.
    """

    pipeline_id: str
    filename: str
    spec_content: str

    @field_validator("pipeline_id")
    @classmethod
    def validate_pipeline_id(cls, v: str) -> str:
        """Require a safe pipeline id."""
        if not _SAFE_PIPELINE_ID_RE.match(v):
            raise ValueError("pipeline_id must be 1-100 chars of letters, digits, '_', or '-'")
        return v

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Require a bare ``*.json`` name with no path separators."""
        name = Path(v).name
        if not name or name != v or not name.endswith(".json"):
            raise ValueError("filename must be a bare *.json name, no path separators")
        return name


class PipelineSpecUploadResponse(BaseModel):
    """Result of a pipeline spec upload.

    Attributes:
        saved_path (str): Path of the stored spec on the host.
    """

    saved_path: str


@app.post("/api/v1/pipeline-spec", response_model=PipelineSpecUploadResponse, dependencies=[Depends(require_api_key)])
def upload_pipeline_spec(req: PipelineSpecUploadRequest) -> PipelineSpecUploadResponse:
    """Store a pipeline spec under ``SDK_ROOT/pipeline_specs/<pipeline_id>/<filename>``.

    Raises:
        HTTPException: 400 if ``spec_content`` is not valid JSON.
    """
    sdk_root = _require_sdk_root()

    try:
        json.loads(req.spec_content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"not valid JSON: {exc}") from exc

    out_dir = sdk_root / "pipeline_specs" / req.pipeline_id
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / req.filename
    dest.write_text(req.spec_content)
    return PipelineSpecUploadResponse(saved_path=str(dest))


_LAUNCHED_LOCK = threading.Lock()
_LAUNCHED_PROCESSES: dict[str, subprocess.Popen] = {}

_STATS_LOG_FILENAME = "axinferencenet_uring.log"
_STATS_LINE_RE = re.compile(
    r"^\[(\d{2}):(\d{2}):(\d{2})\.(\d{6})\] \[STATS\] STATS_JSON (\{.*\})\s*$"
)


def _pipeline_stats_log_path(sdk_root: Path, pipeline_id: str) -> Path:
    """Return the path of a pipeline's stats log, ``SDK_ROOT/pipeline_specs/<pipeline_id>/axinferencenet_uring.log``."""
    return sdk_root / "pipeline_specs" / pipeline_id / _STATS_LOG_FILENAME


def _read_last_stats_line(log_path: Path, max_tail_bytes: int = 65536) -> Optional[re.Match]:
    """Find the last ``STATS_JSON`` line in the tail of a stats log.

    Args:
        log_path (Path): The stats log.
        max_tail_bytes (int, optional): How many bytes from the end of the file to scan. Defaults to 65536.

    Returns:
        Optional[re.Match]: Match of the last stats line, or None if the file is missing or has none in the tail.
    """
    try:
        size = log_path.stat().st_size
    except FileNotFoundError:
        return None
    with log_path.open("rb") as f:
        f.seek(max(0, size - max_tail_bytes))
        data = f.read()
    match = None
    for line in data.decode("utf-8", errors="replace").splitlines():
        m = _STATS_LINE_RE.match(line)
        if m:
            match = m
    return match


class QueueStatsResponse(BaseModel):
    """Latest queue statistics of a running pipeline.

    Every field except ``stats_age_s`` is copied from the ``STATS_JSON`` payload in the pipeline's log.

    Attributes:
        total_frames (int): Frames processed.
        dropped_frames (int): Frames dropped.
        avg_latency_ms (float): Average latency in milliseconds.
        seconds_since_last_success (Optional[float]): Seconds since the last successful request.
        requests_since_last_success (int): Requests since the last success.
        healthy (bool): Health flag reported by the server.
        imdecode_queue_used (int): Entries in use in the image-decode queue.
        imdecode_queue_depth (int): Capacity of the image-decode queue.
        pending_requests (int): Requests waiting.
        node_queues (list[dict]): Per-node queue statistics.
        stats_age_s (float): Seconds since the log line was written, from its time of day (wraps at midnight).
    """

    total_frames: int
    dropped_frames: int
    avg_latency_ms: float
    seconds_since_last_success: Optional[float]
    requests_since_last_success: int
    healthy: bool
    imdecode_queue_used: int
    imdecode_queue_depth: int
    pending_requests: int
    node_queues: list[dict]
    stats_age_s: float


@app.get(
    "/api/v1/pipelines/{pipeline_id}/queue-stats", response_model=QueueStatsResponse,
    dependencies=[Depends(require_api_key)],
)
def get_pipeline_queue_stats(pipeline_id: str) -> QueueStatsResponse:
    """Return the latest queue statistics logged by a launched pipeline.

    Args:
        pipeline_id (str): Pipeline identifier.

    Raises:
        HTTPException: 400 for an invalid id, 404 if the log is missing or has no stats line yet.
    """
    if not _SAFE_PIPELINE_ID_RE.match(pipeline_id):
        raise HTTPException(
            status_code=400, detail="pipeline_id must be 1-100 chars of letters, digits, '_', or '-'",
        )
    sdk_root = _require_sdk_root()
    log_path = _pipeline_stats_log_path(sdk_root, pipeline_id)
    match = _read_last_stats_line(log_path)
    if match is None:
        raise HTTPException(
            status_code=404,
            detail=f"no stats available yet for pipeline '{pipeline_id}' "
                   f"(log not found or has no STATS_JSON line yet: {log_path})",
        )

    hh, mm, ss, us = (int(match.group(i)) for i in range(1, 5))
    payload = json.loads(match.group(5))

    now = time.localtime()
    log_seconds = hh * 3600 + mm * 60 + ss + us / 1e6
    now_seconds = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec + (time.time() % 1.0)
    stats_age_s = now_seconds - log_seconds
    if stats_age_s < 0:
        stats_age_s += 86400

    return QueueStatsResponse(**payload, stats_age_s=round(stats_age_s, 3))


class PipelineLaunchRequest(BaseModel):
    """Request to launch an axinferencenet_grpc process.

    Attributes:
        pipeline_id (str): Identifier used to track and later stop the process.
        port (int): gRPC port the process should listen on.
        spec_path (str): Pipeline spec JSON; must be under ``SDK_ROOT/pipeline_specs``.
        taskset_cpus (Optional[str]): CPU list for ``numactl --physcpubind``.
        membind (Optional[int]): NUMA node for ``numactl --membind``.
        extra_args (Optional[list[str]]): Extra command-line arguments appended to the server command.
    """

    pipeline_id: str
    port: int
    spec_path: str
    taskset_cpus: Optional[str] = None
    membind: Optional[int] = None
    extra_args: Optional[list[str]] = None

    @field_validator("pipeline_id")
    @classmethod
    def validate_pipeline_id(cls, v: str) -> str:
        """Require a safe pipeline id."""
        if not _SAFE_PIPELINE_ID_RE.match(v):
            raise ValueError("pipeline_id must be 1-100 chars of letters, digits, '_', or '-'")
        return v


class PipelineLaunchResponse(BaseModel):
    """Result of a pipeline launch.

    Attributes:
        pid (int): Process id.
        port (int): Port the process is listening on.
    """

    pid: int
    port: int


def _resolve_spec_path(sdk_root: Path, spec_path: str) -> Path:
    """Resolve a spec path and ensure it lies inside ``SDK_ROOT/pipeline_specs``.

    Raises:
        HTTPException: 400 if the path is outside that directory, 404 if the file does not exist.
    """
    specs_root = (sdk_root / "pipeline_specs").resolve()
    resolved = Path(spec_path).resolve()
    if resolved != specs_root and specs_root not in resolved.parents:
        raise HTTPException(
            status_code=400, detail=f"spec_path must be under {specs_root} (got {spec_path})",
        )
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"spec_path does not exist: {resolved}")
    return resolved


@app.post("/api/v1/pipelines/launch", response_model=PipelineLaunchResponse, dependencies=[Depends(require_api_key)])
def launch_pipeline(req: PipelineLaunchRequest) -> PipelineLaunchResponse:
    """Launch an axinferencenet_grpc process for a stored spec and wait until its port is open.

    Any process already tracked under the same ``pipeline_id`` is shut down first.

    Args:
        req (PipelineLaunchRequest): Launch parameters.

    Returns:
        PipelineLaunchResponse: Process id and port.

    Raises:
        HTTPException: 500 if the server binary is missing, 502 if the process fails to start listening.
    """
    sdk_root = _require_sdk_root()
    spec_path = _resolve_spec_path(sdk_root, req.spec_path)
    if not AXINFERENCENET_BIN_PATH.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"AXINFERENCENET_BIN_PATH={AXINFERENCENET_BIN_PATH} does not exist on this server",
        )

    with _LAUNCHED_LOCK:
        existing = _LAUNCHED_PROCESSES.pop(req.pipeline_id, None)
    if existing is not None:
        launch_remote.shutdown_one(existing)

    sdk_venv = os.environ.get("SDK_VENV", "venv")
    try:
        proc = launch_remote.launch_one_with_retry(
            AXINFERENCENET_BIN_PATH, str(spec_path), req.port, sdk_root, req.pipeline_id,
            taskset_cpus=req.taskset_cpus, membind=req.membind, extra_args=req.extra_args,
            sdk_venv=sdk_venv, log_path=_pipeline_stats_log_path(sdk_root, req.pipeline_id),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    with _LAUNCHED_LOCK:
        _LAUNCHED_PROCESSES[req.pipeline_id] = proc
    return PipelineLaunchResponse(pid=proc.pid, port=req.port)


class PipelineShutdownRequest(BaseModel):
    """Request to stop a launched pipeline.

    Attributes:
        pipeline_id (str): Identifier given at launch.
    """

    pipeline_id: str


class PipelineShutdownResponse(BaseModel):
    """Result of a pipeline shutdown.

    Attributes:
        stopped (bool): False if no process was tracked under that id.
    """

    stopped: bool


@app.post(
    "/api/v1/pipelines/shutdown", response_model=PipelineShutdownResponse, dependencies=[Depends(require_api_key)],
)
def shutdown_pipeline(req: PipelineShutdownRequest) -> PipelineShutdownResponse:
    """Stop the process launched under a pipeline id (SIGTERM, then SIGKILL after 10 s)."""
    with _LAUNCHED_LOCK:
        proc = _LAUNCHED_PROCESSES.pop(req.pipeline_id, None)
    if proc is None:
        return PipelineShutdownResponse(stopped=False)
    launch_remote.shutdown_one(proc)
    return PipelineShutdownResponse(stopped=True)


class PipelinesCleanupAllResponse(BaseModel):
    """Result of a global cleanup.

    Attributes:
        killed_pids (list[int]): Pids of axinferencenet processes found and signalled.
        killed_vllm_names (list[str]): Names of tracked vLLM instances that were shut down.
    """

    killed_pids: list[int]
    killed_vllm_names: list[str]


@app.post(
    "/api/v1/pipelines/cleanup-all", response_model=PipelinesCleanupAllResponse,
    dependencies=[Depends(require_api_key)],
)
def cleanup_all_pipelines() -> PipelinesCleanupAllResponse:
    """Stop every axinferencenet process on the host and every tracked vLLM instance.

    Processes are found by scanning ``/proc`` for the binary name, so ones not launched by this server are included. Tracking tables are cleared.
    """

    killed_pids = launch_remote.kill_all_by_name(AXINFERENCENET_BIN_PATH.name)
    with _LAUNCHED_LOCK:
        _LAUNCHED_PROCESSES.clear()
    with _LAUNCHED_VLLM_LOCK:
        vllm_snapshot = dict(_LAUNCHED_VLLM_PROCESSES)
        _LAUNCHED_VLLM_PROCESSES.clear()
    for proc, _port, _context_length in vllm_snapshot.values():
        launch_remote.shutdown_one(proc)
    return PipelinesCleanupAllResponse(
        killed_pids=killed_pids, killed_vllm_names=sorted(vllm_snapshot),
    )


_VLLM_AXELERA_DIR = Path(os.environ.get("VLLM_AXELERA_DIR", _REPO_ROOT / "server" / "vllm" / "axelera"))
_VLLM_VENV_PYTHON = Path(os.environ.get("VLLM_VENV_PYTHON", _REPO_ROOT / ".venv-vllm" / "bin" / "python3"))
_VLLM_LOG_DIR = Path(os.environ.get("VLLM_LOG_DIR", DEPLOYMENT_DIR / "vllm_logs"))

_LAUNCHED_VLLM_LOCK = threading.Lock()
_LAUNCHED_VLLM_PROCESSES: dict[str, tuple[subprocess.Popen, int, Optional[int]]] = {}


class VllmArtifactInfo(BaseModel):
    """A compiled vLLM artifact.

    Attributes:
        name (str): Directory name under ``build``.
        artifact_path (str): ``${SDK_ROOT}``-prefixed path of its ``axscript`` directory.
    """

    name: str
    artifact_path: str


class VllmArtifactsResponse(BaseModel):
    """Available vLLM artifacts.

    Attributes:
        artifacts (list[VllmArtifactInfo]): Directories under ``SDK_ROOT/build`` that contain ``axscript``.
    """

    artifacts: list[VllmArtifactInfo]


@app.get(
    "/api/v1/vllm/artifacts", response_model=VllmArtifactsResponse, dependencies=[Depends(require_api_key)],
)
def list_vllm_artifacts() -> VllmArtifactsResponse:
    """List ``SDK_ROOT/build/*/axscript`` directories usable as vLLM artifacts."""
    sdk_root = _require_sdk_root()
    artifacts = []
    build_dir = sdk_root / "build"
    if build_dir.is_dir():
        for model_dir in sorted(p for p in build_dir.iterdir() if p.is_dir()):
            if (model_dir / "axscript").is_dir():
                artifacts.append(VllmArtifactInfo(
                    name=model_dir.name,
                    artifact_path=f"${{SDK_ROOT}}/build/{model_dir.name}/axscript",
                ))
    return VllmArtifactsResponse(artifacts=artifacts)


def _resolve_vllm_artifact(sdk_root: Path, artifact: str) -> Path:
    """Resolve an artifact path, expanding ``${SDK_ROOT}`` and treating relative paths as SDK-root relative.

    Raises:
        HTTPException: 400 if the directory does not exist.
    """
    resolved = Path(artifact.replace("${SDK_ROOT}", str(sdk_root)))
    if not resolved.is_absolute():
        resolved = sdk_root / resolved
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"artifact directory not found on this host: {resolved}")
    return resolved


def _read_vllm_artifact_context_length(artifact_dir: Path) -> Optional[int]:
    """Read ``context_len`` from ``vlm.json`` or ``pipeline.json`` in an artifact directory.

    Returns:
        Optional[int]: The first value found, or None if no manifest provides one.
    """

    candidates = [
        artifact_dir / "vlm.json",
        artifact_dir / "pipeline.json",
    ]
    for manifest_path in candidates:
        if not manifest_path.is_file():
            continue
        try:
            data = json.loads(manifest_path.read_text())
            return int(data["context_len"])
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return None


class VllmLaunchRequest(BaseModel):
    """Request to launch a vLLM server.

    Attributes:
        name (str): Identifier used to track the instance and name its log.
        artifact (str): Artifact directory; may use ``${SDK_ROOT}``.
        port (int): Port to serve on.
        device (str): Value exported to serve.sh as ``DEVICE``.
        enable_thinking (bool): Sets ``THINKING`` to ``on`` or ``off``.
        temperature (float): Sampling temperature exported as ``TEMPERATURE``.
    """

    name: str
    artifact: str
    port: int
    device: str
    enable_thinking: bool = False
    temperature: float = 0.0

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Require a safe instance name."""
        if not _SAFE_PIPELINE_ID_RE.match(v):
            raise ValueError("name must be 1-100 chars of letters, digits, '_', or '-'")
        return v


class VllmLaunchResponse(BaseModel):
    """Result of a vLLM launch.

    Attributes:
        pid (int): Process id.
        port (int): Port being served.
        context_length (Optional[int]): Context length read from the artifact, if known.
    """

    pid: int
    port: int
    context_length: Optional[int] = None


@app.post("/api/v1/vllm/launch", response_model=VllmLaunchResponse, dependencies=[Depends(require_api_key)])
def launch_vllm(req: VllmLaunchRequest) -> VllmLaunchResponse:
    """Launch a vLLM server with ``server/vllm/axelera/scripts/serve.sh`` and wait up to 180 s for its port.

    Output goes to ``vllm_logs/<name>.log``. An instance already tracked under the same name is shut down first.

    Args:
        req (VllmLaunchRequest): Launch parameters.

    Returns:
        VllmLaunchResponse: Process id, port and context length.

    Raises:
        HTTPException: 400 if the artifact is missing, 500 if serve.sh or the vLLM venv is missing, 502 if the server exits or does not open its port.
    """
    sdk_root = _require_sdk_root()
    artifact_dir = _resolve_vllm_artifact(sdk_root, req.artifact)
    serve_script = _VLLM_AXELERA_DIR / "scripts" / "serve.sh"
    if not serve_script.is_file():
        raise HTTPException(status_code=500, detail=f"serve.sh not found at {serve_script}")
    if not _VLLM_VENV_PYTHON.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"VLLM_VENV_PYTHON={_VLLM_VENV_PYTHON} does not exist on this server "
                   "(run setup.sh --vllm-axplugin, see server/quickstart.md)",
        )

    with _LAUNCHED_VLLM_LOCK:
        existing = _LAUNCHED_VLLM_PROCESSES.pop(req.name, None)
    if existing is not None:
        launch_remote.shutdown_one(existing[0])

    context_length = _read_vllm_artifact_context_length(artifact_dir)

    _VLLM_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _VLLM_LOG_DIR / f"{req.name}.log"

    env = dict(os.environ)
    env["MODEL"] = str(artifact_dir)
    env["PORT"] = str(req.port)
    env["DEVICE"] = req.device
    env["THINKING"] = "on" if req.enable_thinking else "off"
    env["TEMPERATURE"] = str(req.temperature)
    env["AXELERA_PYTHON"] = str(_VLLM_VENV_PYTHON)
    env["PYTHONPATH"] = str(sdk_root)

    with log_path.open("wb") as log_file:
        proc = subprocess.Popen(
            ["bash", str(serve_script)],
            cwd=str(_VLLM_AXELERA_DIR), env=env,
            stdin=subprocess.DEVNULL, stdout=log_file, stderr=subprocess.STDOUT,
        )

    try:
        launch_remote.wait_for_port(proc, req.port, req.name, timeout_s=180)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"{exc} -- see {log_path}") from exc

    with _LAUNCHED_VLLM_LOCK:
        _LAUNCHED_VLLM_PROCESSES[req.name] = (proc, req.port, context_length)
    return VllmLaunchResponse(pid=proc.pid, port=req.port, context_length=context_length)


class VllmShutdownRequest(BaseModel):
    """Request to stop a vLLM instance.

    Attributes:
        name (str): Name given at launch.
    """

    name: str


class VllmShutdownResponse(BaseModel):
    """Result of a vLLM shutdown.

    Attributes:
        stopped (bool): False if no instance was tracked under that name.
    """

    stopped: bool


@app.post(
    "/api/v1/vllm/shutdown", response_model=VllmShutdownResponse, dependencies=[Depends(require_api_key)],
)
def shutdown_vllm(req: VllmShutdownRequest) -> VllmShutdownResponse:
    """Stop the vLLM instance launched under a name."""
    with _LAUNCHED_VLLM_LOCK:
        existing = _LAUNCHED_VLLM_PROCESSES.pop(req.name, None)
    if existing is None:
        return VllmShutdownResponse(stopped=False)
    launch_remote.shutdown_one(existing[0])
    return VllmShutdownResponse(stopped=True)


class VllmStatusInfo(BaseModel):
    """Status of one tracked vLLM instance.

    Attributes:
        name (str): Instance name.
        pid (int): Process id.
        port (int): Port served.
        running (bool): Whether the process is still alive.
        context_length (Optional[int]): Context length read from the artifact, if known.
    """

    name: str
    pid: int
    port: int
    running: bool
    context_length: Optional[int] = None


class VllmStatusResponse(BaseModel):
    """Tracked vLLM instances.

    Attributes:
        instances (list[VllmStatusInfo]): One entry per tracked instance.
    """

    instances: list[VllmStatusInfo]


@app.get("/api/v1/vllm/status", response_model=VllmStatusResponse, dependencies=[Depends(require_api_key)])
def vllm_status() -> VllmStatusResponse:
    """List vLLM instances launched through this server and whether each is still running."""
    with _LAUNCHED_VLLM_LOCK:
        snapshot = dict(_LAUNCHED_VLLM_PROCESSES)
    instances = [
        VllmStatusInfo(name=name, pid=proc.pid, port=port, running=proc.poll() is None, context_length=context_length)
        for name, (proc, port, context_length) in snapshot.items()
    ]
    return VllmStatusResponse(instances=instances)


class BenchmarkMediaFetchResult(BaseModel):
    """Outcome for one benchmark media file.

    Attributes:
        file (str): Final file name.
        status (Literal["already_exists", "downloaded", "transcoded", "error"]): What happened.
        detail (str): Error text when ``status`` is ``error``.
    """

    file: str
    status: Literal["already_exists", "downloaded", "transcoded", "error"]
    detail: str = ""


class BenchmarkMediaFetchStartResponse(BaseModel):
    """Acknowledgement that a media fetch was started.

    Attributes:
        started (bool): Always True when returned.
    """

    started: bool


class BenchmarkMediaStatusResponse(BaseModel):
    """Progress of the benchmark media fetch.

    Attributes:
        running (bool): Whether a fetch is in progress.
        current_file (Optional[str]): File being produced.
        stage (Optional[str]): ``downloading``, ``transferring`` or ``preprocessing``.
        results (list[BenchmarkMediaFetchResult]): Files handled so far.
        total (int): Number of files in the plan.
        ok (Optional[bool]): None until a run finishes, then True if no file failed.
    """

    running: bool
    current_file: Optional[str] = None
    stage: Optional[str] = None
    results: list[BenchmarkMediaFetchResult] = []
    total: int
    ok: Optional[bool] = None


_BENCHMARK_MEDIA_DIR = _REPO_ROOT / "client" / "assets" / "test_images"

# Final file name -> (catalog file to download as is, catalog file to downsample, target height). Exactly one of the first two is set.
_BENCHMARK_MEDIA_PLAN: dict[str, tuple[Optional[str], Optional[str], Optional[int]]] = {
    "traffic_480p.mp4": ("h264/traffic1_480p.mp4", None, None),
    "traffic_720p.mp4": ("h264/traffic1_720p.mp4", None, None),
    "traffic_1080p.mp4": ("h264/traffic1_1080p.mp4", None, None),
    "intersection_1080p.mp4": ("h264/intersection1_1080p.mp4", None, None),
    "intersection_720p.mp4": (None, "h264/intersection1_1080p.mp4", 720),
    "intersection_480p.mp4": (None, "h264/intersection1_1080p.mp4", 480),
    "dancing_1080p.mp4": (None, "h264/dancing_4k.mp4", 1080),
    "dancing_720p.mp4": (None, "h264/dancing_4k.mp4", 720),
    "dancing_480p.mp4": (None, "h264/dancing_4k.mp4", 480),
}

_benchmark_media_lock = threading.Lock()

_benchmark_media_progress: dict = {
    "running": False,
    "current_file": None,
    "stage": None,
    "results": [],
    "total": len(_BENCHMARK_MEDIA_PLAN),
    "ok": None,
}


def _axdownloadmedia_path(sdk_root: Path) -> Path:
    """Return the axdownloadmedia binary in the SDK venv.

    Raises:
        HTTPException: 500 if it does not exist.
    """
    sdk_venv = os.environ.get("SDK_VENV", "venv")
    axdownloadmedia = sdk_root / sdk_venv / "bin" / "axdownloadmedia"
    if not axdownloadmedia.is_file():
        raise HTTPException(status_code=500, detail=f"axdownloadmedia not found at {axdownloadmedia}")
    return axdownloadmedia


def _ensure_catalog_media(axdownloadmedia: Path, sdk_root: Path, media_dir: Path, catalog_name: str) -> Path:
    """Make sure a catalog media file exists under ``media_dir``, downloading it with axdownloadmedia if needed.

    Args:
        axdownloadmedia (Path): The axdownloadmedia binary.
        sdk_root (Path): The SDK root directory.
        media_dir (Path): Download directory.
        catalog_name (str): Catalog file name, e.g. ``h264/traffic1_480p.mp4``.

    Returns:
        Path: The local file.

    Raises:
        RuntimeError: If the download fails or the file is still absent.
    """
    dest = media_dir / catalog_name
    if dest.is_file():
        return dest
    env = os.environ.copy()
    env["AXELERA_FRAMEWORK"] = _axelera_framework_value(sdk_root)
    result = subprocess.run(
        [str(axdownloadmedia), catalog_name, "--output", str(media_dir)],
        capture_output=True, text=True, env=env, cwd=str(sdk_root), check=False,
    )
    if result.returncode != 0 or not dest.is_file():
        raise RuntimeError(
            f"axdownloadmedia failed for {catalog_name!r}: "
            f"{(result.stderr.strip() or result.stdout.strip())[-2000:]}"
        )
    return dest


def _ffmpeg_downsample(src: Path, dest: Path, height: int) -> None:
    """Re-encode a video to the given height with ffmpeg (H.264, CRF 20, audio dropped, width scaled to keep the aspect ratio).

    Args:
        src (Path): Source video.
        dest (Path): Output file.
        height (int): Target height in pixels.

    Raises:
        RuntimeError: If ffmpeg fails or produces no file.
    """
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    result = subprocess.run(
        [ffmpeg, "-y", "-i", str(src), "-vf", f"scale=-2:{height}",
         "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-an", str(dest)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0 or not dest.is_file():
        raise RuntimeError(f"ffmpeg downsample to {height}p failed: {result.stderr.strip()[-2000:]}")


def _run_benchmark_media_fetch(sdk_root: Path, axdownloadmedia: Path) -> None:
    """Thread body that produces every file in ``_BENCHMARK_MEDIA_PLAN`` and records progress.

    Files that already exist are skipped, others are downloaded or transcoded; a failure on one file is recorded and the run continues.

    Note:
        Releases ``_benchmark_media_lock``, which the caller must have acquired.

    Args:
        sdk_root (Path): The SDK root directory.
        axdownloadmedia (Path): The axdownloadmedia binary.
    """

    progress = _benchmark_media_progress
    progress.update(running=True, current_file=None, stage=None, results=[], ok=None)
    try:
        for final_name, (native_name, ffmpeg_source_name, height) in _BENCHMARK_MEDIA_PLAN.items():
            dest = _BENCHMARK_MEDIA_DIR / final_name
            if dest.is_file():
                progress["results"].append({"file": final_name, "status": "already_exists", "detail": ""})
                continue
            progress["current_file"] = final_name
            try:
                if native_name is not None:
                    progress["stage"] = "downloading"
                    local = _ensure_catalog_media(axdownloadmedia, sdk_root, _BENCHMARK_MEDIA_DIR, native_name)
                    if local != dest:
                        progress["stage"] = "transferring"
                        shutil.copyfile(local, dest)
                    progress["results"].append({"file": final_name, "status": "downloaded", "detail": ""})
                else:
                    progress["stage"] = "downloading"
                    source_local = _ensure_catalog_media(
                        axdownloadmedia, sdk_root, _BENCHMARK_MEDIA_DIR, ffmpeg_source_name
                    )
                    progress["stage"] = "preprocessing"
                    _ffmpeg_downsample(source_local, dest, height)
                    progress["results"].append({"file": final_name, "status": "transcoded", "detail": ""})
            except Exception as exc:
                progress["results"].append({"file": final_name, "status": "error", "detail": str(exc)[-500:]})
        progress["ok"] = all(r["status"] != "error" for r in progress["results"])
    finally:
        progress["current_file"] = None
        progress["stage"] = None
        progress["running"] = False
        _benchmark_media_lock.release()


@app.post(
    "/api/v1/benchmark-media/fetch", response_model=BenchmarkMediaFetchStartResponse,
    dependencies=[Depends(require_api_key)],
)
def fetch_benchmark_media() -> BenchmarkMediaFetchStartResponse:
    """Start a background fetch of the benchmark media files.

    Raises:
        HTTPException: 500 if axdownloadmedia is missing, 409 if a fetch is already running.
    """

    sdk_root = _require_sdk_root()
    axdownloadmedia = _axdownloadmedia_path(sdk_root)
    _BENCHMARK_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    if not _benchmark_media_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="a benchmark media fetch is already running on this host")
    threading.Thread(target=_run_benchmark_media_fetch, args=(sdk_root, axdownloadmedia), daemon=True).start()
    return BenchmarkMediaFetchStartResponse(started=True)


@app.get(
    "/api/v1/benchmark-media/status", response_model=BenchmarkMediaStatusResponse,
    dependencies=[Depends(require_api_key)],
)
def benchmark_media_status() -> BenchmarkMediaStatusResponse:
    """Report progress of the benchmark media fetch."""
    progress = _benchmark_media_progress
    return BenchmarkMediaStatusResponse(
        running=progress["running"],
        current_file=progress["current_file"],
        stage=progress["stage"],
        results=[BenchmarkMediaFetchResult(**r) for r in progress["results"]],
        total=progress["total"],
        ok=progress["ok"],
    )
