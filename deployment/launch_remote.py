"""Start and stop axinferencenet_grpc processes for an already-compiled pipeline spec.

Exposes launch_server, wait_for_port, launch_one_with_retry, shutdown_one, find_pids_by_name and kill_all_by_name. host_server.py calls them from its pipeline and vLLM launch and shutdown endpoints.

Note:
    From the spec JSON only the ``global`` block and the ``meta_key`` and ``role`` of each net are read; nothing is recompiled.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PORT_OPEN_TIMEOUT_S = 60
_SHUTDOWN_TIMEOUT_S = 10
_MAX_LAUNCH_RETRIES = 3

# Image-decode threads per pinned CPU; used only when pinned and the spec has no explicit value.
_IMDECODE_THREADS_PER_CPU = 4


def _numactl_prefix(taskset_cpus: Optional[str], membind: Optional[int]) -> list[str]:
    """Build the numactl argv prefix for a pinned launch.

    Args:
        taskset_cpus (Optional[str]): CPU list such as ``0-3,8``; falsy means unpinned.
        membind (Optional[int]): NUMA node for ``--membind``, or None to omit it.

    Returns:
        list[str]: The prefix, or an empty list when unpinned.
    """
    if not taskset_cpus:
        return []
    prefix = ["numactl", f"--physcpubind={taskset_cpus}"]
    if membind is not None:
        prefix.append(f"--membind={membind}")
    return prefix


def _count_cpus(taskset_cpus: str) -> int:
    """Count the CPUs in a comma-separated list of ids and inclusive ranges.

    Args:
        taskset_cpus (str): CPU list such as ``0-3,8``.

    Returns:
        int: Number of CPUs listed.
    """
    total = 0
    for part in taskset_cpus.split(","):
        if "-" in part:
            lo, hi = part.split("-")
            total += int(hi) - int(lo) + 1
        else:
            total += 1
    return total


def _imdecode_threads_for(taskset_cpus: Optional[str], override: Optional[int] = None) -> Optional[int]:
    """Choose the image-decode thread count for one pipeline.

    Args:
        taskset_cpus (Optional[str]): CPU list the pipeline is pinned to, if any.
        override (Optional[int], optional): Explicit value from the spec; wins when given.

    Returns:
        Optional[int]: The override, else ``_IMDECODE_THREADS_PER_CPU`` times the pinned CPU count, else None.
    """
    if override is not None:
        return override
    if not taskset_cpus:
        return None
    return _IMDECODE_THREADS_PER_CPU * _count_cpus(taskset_cpus)


def _global_settings_from_spec(pipeline_json_path: str) -> dict:
    """Return the ``global`` block of a pipeline spec JSON file."""
    return json.loads(Path(pipeline_json_path).read_text())["global"]


def _meta_key_roles_from_spec(pipeline_json_path: str) -> dict[str, str]:
    """Map each net's ``meta_key`` to its ``role`` from a pipeline spec JSON file.

    Nets lacking either field are skipped.
    """
    nets = json.loads(Path(pipeline_json_path).read_text()).get("nets", {})
    return {
        net["meta_key"]: net["role"]
        for net in nets.values()
        if net.get("meta_key") and net.get("role")
    }


def launch_server(
    bin_path: Path,
    pipeline_json_path: str,
    port: int,
    sdk_root: Path,
    pipeline_id: str,
    taskset_cpus: Optional[str] = None,
    membind: Optional[int] = None,
    extra_args: Optional[list[str]] = None,
    sdk_venv: str = "venv",
    log_path: Optional[Path] = None,
) -> subprocess.Popen:
    """Start one axinferencenet_grpc process for a pipeline spec, without waiting for it to listen.

    The command line is built from the spec's ``global`` block (output format, timeout, restart interval, watchdog and image-decode settings) and ``meta_key``/``role`` pairs, prefixed with numactl when CPUs are given. It runs under ``bash -c`` after activating the SDK venv and exporting ``AXELERA_FRAMEWORK`` and ``LD_LIBRARY_PATH``. The environment also gets ``GRPC_OUTPUT_FORMAT`` and, if ``log_path`` is set, ``URING_LOG_PATH``.

    Args:
        bin_path (Path): The axinferencenet_grpc binary.
        pipeline_json_path (str): Compiled pipeline spec JSON.
        port (int): Port for the server to listen on.
        sdk_root (Path): SDK root; also the working directory.
        pipeline_id (str): Name used in log messages.
        taskset_cpus (Optional[str], optional): CPU list for ``numactl --physcpubind``.
        membind (Optional[int], optional): NUMA node for ``numactl --membind``.
        extra_args (Optional[list[str]], optional): Arguments appended to the server command.
        sdk_venv (str, optional): Venv directory name under the SDK root. Defaults to ``venv``.
        log_path (Optional[Path], optional): Where the server writes its stats log.

    Returns:
        subprocess.Popen: The running process.

    Raises:
        KeyError: If the spec's ``global`` block lacks ``im_decode_output_format``, ``timeout_s`` or ``restart_interval_s``.
    """

    g = _global_settings_from_spec(pipeline_json_path)
    imdecode_threads = _imdecode_threads_for(taskset_cpus, g.get("imdecode_threads"))
    imdecode_queue_depth = g.get("imdecode_queue_depth")
    imdecode_queue_timeout_ms = g.get("imdecode_queue_timeout_ms")
    meta_key_roles = _meta_key_roles_from_spec(pipeline_json_path)
    argv = _numactl_prefix(taskset_cpus, membind) + [
        str(bin_path),
        "--pipeline-spec", pipeline_json_path,
        "--port", str(port),
        "--output-format", g["im_decode_output_format"],
        "--timeout", str(g["timeout_s"]),
        "--restart-interval", str(g["restart_interval_s"]),
        "--watchdog-timeout-ms", str(g.get("watchdog_timeout_ms", 0)),
        *(["--imdecode-threads", str(imdecode_threads)] if imdecode_threads is not None else []),
        *(["--imdecode-queue-depth", str(imdecode_queue_depth)] if imdecode_queue_depth is not None else []),
        *(["--imdecode-queue-timeout-ms", str(imdecode_queue_timeout_ms)]
          if imdecode_queue_timeout_ms is not None else []),
        *[a for key, role in meta_key_roles.items() for a in ("--meta-key-role", f"{key}={role}")],
        *(extra_args or []),
    ]
    env = dict(os.environ)
    env["GRPC_OUTPUT_FORMAT"] = g["im_decode_output_format"]
    if log_path is not None:
        env["URING_LOG_PATH"] = str(log_path)
    cmd = (
        f'source "{sdk_root}/{sdk_venv}/bin/activate" && '
        f'export AXELERA_FRAMEWORK="{sdk_root}" && '
        f'export LD_LIBRARY_PATH="{sdk_root}/operators/lib:${{LD_LIBRARY_PATH:-}}" && '
        f'exec {" ".join(shlex.quote(a) for a in argv)}'
    )
    logger.info(
        "launching pipeline '%s' -> port %d%s%s%s%s%s",
        pipeline_id, port,
        f" (pinned: {' '.join(_numactl_prefix(taskset_cpus, membind))})" if taskset_cpus else "",
        f" (imdecode-threads={imdecode_threads})" if imdecode_threads is not None else "",
        f" (imdecode-queue-depth={imdecode_queue_depth})" if imdecode_queue_depth is not None else "",
        f" (imdecode-queue-timeout-ms={imdecode_queue_timeout_ms})" if imdecode_queue_timeout_ms is not None else "",
        f" (meta-key-roles={meta_key_roles})" if meta_key_roles else "",
    )
    return subprocess.Popen(["bash", "-c", cmd], cwd=str(sdk_root), env=env)


def _port_open(port: int) -> bool:
    """Return True if something accepts TCP connections on 127.0.0.1 at the port (0.5 s connect timeout)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_for_port(
    proc: subprocess.Popen, port: int, pipeline_id: str, timeout_s: float = _PORT_OPEN_TIMEOUT_S,
) -> None:
    """Wait until a launched process accepts connections on its port.

    Args:
        proc (subprocess.Popen): The launched process.
        port (int): Port to probe on 127.0.0.1.
        pipeline_id (str): Name used in error messages.
        timeout_s (float, optional): Seconds to wait. Defaults to ``_PORT_OPEN_TIMEOUT_S``.

    Raises:
        RuntimeError: If the process exits first or the port never opens.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"pipeline '{pipeline_id}' exited early (code {proc.returncode}) "
                "before opening its port"
            )
        if _port_open(port):
            return
        time.sleep(0.5)
    raise RuntimeError(f"pipeline '{pipeline_id}' never opened port {port}")


def launch_one_with_retry(
    bin_path: Path,
    pipeline_json_path: str,
    port: int,
    sdk_root: Path,
    pipeline_id: str,
    taskset_cpus: Optional[str] = None,
    membind: Optional[int] = None,
    extra_args: Optional[list[str]] = None,
    sdk_venv: str = "venv",
    log_path: Optional[Path] = None,
) -> subprocess.Popen:
    """Launch a pipeline and wait for its port, relaunching if the process dies from a signal.

    Up to ``_MAX_LAUNCH_RETRIES`` attempts are made; a failed attempt is retried only when the process was killed by a signal, otherwise the error is raised. Arguments are those of ``launch_server``.

    Returns:
        subprocess.Popen: The process, once its port is open.

    Raises:
        RuntimeError: If the process exits early or never opens its port on the final or a non-crash attempt.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, _MAX_LAUNCH_RETRIES + 1):
        proc = launch_server(
            bin_path, pipeline_json_path, port, sdk_root, pipeline_id,
            taskset_cpus, membind, extra_args, sdk_venv, log_path,
        )
        try:
            wait_for_port(proc, port, pipeline_id)
            return proc
        except RuntimeError as exc:
            last_exc = exc
            crashed = proc.returncode is not None and proc.returncode < 0
            if crashed and attempt < _MAX_LAUNCH_RETRIES:
                logger.warning(
                    "pipeline '%s' crashed (signal %d) on attempt %d/%d -- "
                    "relaunching a fresh process",
                    pipeline_id, -proc.returncode, attempt, _MAX_LAUNCH_RETRIES,
                )
                continue
            raise
    raise last_exc


def shutdown_one(proc: subprocess.Popen) -> None:
    """Stop a process with SIGTERM, escalating to SIGKILL after ``_SHUTDOWN_TIMEOUT_S`` seconds.

    Does nothing if the process has already exited.
    """
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=_SHUTDOWN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        logger.warning(
            "pid=%d did not exit within %ds of SIGTERM -- SIGKILL", proc.pid, _SHUTDOWN_TIMEOUT_S,
        )
        proc.kill()
        proc.wait()


def find_pids_by_name(name_prefix: str) -> list[int]:
    """Find processes whose executable name starts with a prefix, by scanning ``/proc``.

    Args:
        name_prefix (str): Prefix to match against the base name of each process's argv[0].

    Returns:
        list[int]: Matching pids; unreadable entries are skipped.
    """
    pids = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            cmdline = (Path("/proc") / entry / "cmdline").read_bytes()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        argv0 = cmdline.split(b"\0", 1)[0].decode(errors="replace")
        if os.path.basename(argv0).startswith(name_prefix):
            pids.append(int(entry))
    return pids


def _pid_alive(pid: int) -> bool:
    """Return True if a pid exists (a permission error counts as alive)."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def kill_all_by_name(name_prefix: str) -> list[int]:
    """Terminate every process whose name starts with a prefix.

    Sends SIGTERM, waits up to ``_SHUTDOWN_TIMEOUT_S`` seconds, then sends SIGKILL to survivors. Processes owned by other users are logged and skipped.

    Args:
        name_prefix (str): Prefix matched by ``find_pids_by_name``.

    Returns:
        list[int]: Pids that were found, including ones that exited on their own.
    """

    pids = find_pids_by_name(name_prefix)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            logger.warning("no permission to SIGTERM pid=%d (%s) -- owned by another user?", pid, name_prefix)

    deadline = time.monotonic() + _SHUTDOWN_TIMEOUT_S
    remaining = set(pids)
    while remaining and time.monotonic() < deadline:
        remaining = {pid for pid in remaining if _pid_alive(pid)}
        if remaining:
            time.sleep(0.2)

    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
            logger.warning("pid=%d (%s) did not exit within %ds of SIGTERM -- SIGKILL", pid, name_prefix, _SHUTDOWN_TIMEOUT_S)
        except (ProcessLookupError, PermissionError):
            pass

    return pids
