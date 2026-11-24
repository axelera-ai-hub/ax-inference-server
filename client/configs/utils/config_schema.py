"""Pydantic schema and loader for the inference server YAML config.

Defines ServerConfig and its sections (global settings, nets, predicates, graph pipelines,
legacy instances) with cross-reference validation, plus load_config() to read a file.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


_AXNET_CONFIG_RE = re.compile(
    r'^(net-[a-zA-Z0-9]+;devices:[0-9]+(,[0-9]+)*-[0-9]+(;(?=net-))?)+$'
)

_VALID_OUTPUT_FORMATS = {"BGR", "RGBA", "I420"}
_VALID_OPENCL_FLAGS = {"--enable-opencl", "--disable-opencl"}


def _check_output_format(v: str) -> None:
    """Validate a decoded-frame colour format name.

    Raises:
        ValueError: If v is not one of BGR, RGBA or I420.
    """
    if v not in _VALID_OUTPUT_FORMATS:
        raise ValueError(
            f"grpc_output_format must be one of {sorted(_VALID_OUTPUT_FORMATS)}, got {v!r}"
        )


class GlobalSettings(BaseModel):
    """The 'global:' section of the server config: settings shared by every instance and pipeline.

    Some fields only apply to the legacy 'instances:' mode (axnet_model_path, grpc_output_format,
    use_axinference_net_opencl, timeout, flush_thres) and others only to 'pipelines:'
    (watchdog_timeout_ms, result_queue_depth). The per-field descriptions state which.

    Note:
        sdk_root falls back to the $SDK_ROOT environment variable when omitted; validation fails if neither is set.
    """

    axnet_model_path: Optional[str] = Field(default=None, description="Path to the compiled .axnet model file (required for instances:, not needed for pipelines:)")
    sdk_root: str = Field(
        default="",
        description="Path to the Voyager SDK root directory. If omitted from the "
                    "YAML, derived from the $SDK_ROOT environment variable (see "
                    "_derive_sdk_root_from_env below) -- set one or the other.",
    )
    grpc_output_format: Optional[str] = Field(
        default=None,
        description="BGR | RGBA | I420 — required for instances: (legacy mode); "
                    "pipelines: entries set their own im_decode_output_format instead",
    )
    use_axinference_net_opencl: Optional[str] = Field(
        default=None, description="--enable-opencl | --disable-opencl (required for instances:)"
    )
    sdk_venv: str = Field(
        default="venv",
        description="Name of the venv directory under sdk_root (e.g. 'venv-sdk180' "
                    "on a host with multiple SDK venvs side by side) -- "
                    "server/models/utils/axnet.py sources '{sdk_root}/{sdk_venv}/bin/activate' "
                    "rather than assuming the local dev box's own 'venv' name always applies.",
    )
    use_simd_decode: int = Field(default=1, description="0 = OpenCV decoder; 1 = TurboJPEG SIMD")
    restart_interval: int = Field(default=0, description="Auto-restart interval (seconds); 0 = disabled")
    watchdog_timeout_ms: int = Field(default=0, description="Health-watchdog auto-restart threshold (ms) — pipelines: only; restarts if no successful completion despite request attempts; 0 = disabled")
    timeout: int = Field(default=5, description="Server-side request timeout (seconds) — legacy instances: mode only; pipelines: entries set their own timeout instead")
    flush_thres: int = Field(default=4850, description="Pipeline flush threshold (milliseconds) — legacy instances: mode only; pipelines: entries set their own flush_thres instead")
    pipeline_depth: Optional[int] = Field(default=None, description="Max in-flight frames (omitted if unset)")
    result_queue_depth: Optional[int] = Field(
        default=None,
        description="Capacity of the pipeline-wide result_queue_ shared by every "
                    "InferenceNode/LoopGuardNode drop-sink and the terminal sink node "
                    "(pipelines: only). Omitted (default) auto-derives from the "
                    "pipeline's own node count in the C++ builder; set explicitly to override.",
    )
    docker_image: str = Field(
        default="axelera-grpc-server:latest",
        description="Docker image for inference containers",
    )

    @field_validator("grpc_output_format")
    @classmethod
    def _validate_output_format(cls, v: Optional[str]) -> Optional[str]:
        """Check grpc_output_format against the allowed formats when it is set."""
        if v is not None:
            _check_output_format(v)
        return v

    @field_validator("use_axinference_net_opencl")
    @classmethod
    def _validate_opencl_flag(cls, v: Optional[str]) -> Optional[str]:
        """Check use_axinference_net_opencl is '--enable-opencl' or '--disable-opencl' when set."""
        if v is not None and v not in _VALID_OPENCL_FLAGS:
            raise ValueError(
                f"use_axinference_net_opencl must be one of {sorted(_VALID_OPENCL_FLAGS)}, got {v!r}"
            )
        return v

    @model_validator(mode="before")
    @classmethod
    def _derive_sdk_root_from_env(cls, data: Any) -> Any:
        """Fill an empty or missing sdk_root from $SDK_ROOT before field validation (mutates the input dict)."""
        if isinstance(data, dict) and not data.get("sdk_root"):
            data["sdk_root"] = os.environ.get("SDK_ROOT", "")
        return data

    @field_validator("sdk_root")
    @classmethod
    def _validate_sdk_root_non_empty(cls, v: str) -> str:
        """Require sdk_root to be non-blank after the environment fallback."""
        if not v or not v.strip():
            raise ValueError(
                "must be a non-empty string -- set global.sdk_root in the YAML "
                "or export the $SDK_ROOT environment variable"
            )
        return v


class InstanceConfig(BaseModel):
    """One legacy single-net inference instance (an entry of 'instances:').

    Attributes:
        id (int): Instance index; ids across the config must be 0..N-1.
        grpc_port (int): Host port for the gRPC server.
        grpc_axnet_config (str): Axnet config string, validated against the net/devices/cores syntax.
        taskset_cpus (Optional[str]): CPU list applied with numactl --physcpubind.
        membind (Optional[int]): NUMA node for numactl --membind.
    """

    id: int = Field(..., description="Unique instance index (0-based)")
    grpc_port: int = Field(..., description="gRPC port published on the host (1024-65535)")
    grpc_axnet_config: str = Field(
        ..., description="Axnet config string, e.g. 'net-0;devices:0-4'"
    )
    taskset_cpus: Optional[str] = Field(
        default=None,
        description="CPU affinity string (e.g. '0-7'); omit on ARM. Despite the "
                    "field name, this is applied via 'numactl --physcpubind', "
                    "never the 'taskset' binary.",
    )
    membind: Optional[int] = Field(
        default=None,
        description="NUMA node for memory binding (numactl --membind); omit on "
                    "single-socket hosts. Only applied when taskset_cpus is also set.",
    )

    @field_validator("grpc_port")
    @classmethod
    def _validate_port(cls, v: int) -> int:
        """Require grpc_port to be within 1024-65535."""
        if not (1024 <= v <= 65535):
            raise ValueError(f"grpc_port must be in 1024-65535, got {v}")
        return v

    @field_validator("grpc_axnet_config")
    @classmethod
    def _validate_axnet_config(cls, v: str) -> str:
        """Require grpc_axnet_config to match 'net-<name>;devices:<ids>-<cores>[;net-...]'."""
        if not _AXNET_CONFIG_RE.match(v):
            raise ValueError(
                f"grpc_axnet_config {v!r} does not match expected syntax "
                "'net-<name>;devices:<id>[,<id>...]-<cores>[;net-...]'"
            )
        return v

    def to_env_vars(self, g: GlobalSettings) -> dict[str, str]:
        """Build the environment variables passed to this instance's container.

        Args:
            g (GlobalSettings): Global settings supplying format, SDK root, timeouts and decode options.

        Returns:
            dict[str, str]: Variable name to string value. pipeline_depth, taskset_cpus_0 and
            membind_0 are included only when set.
        """
        env: dict[str, str] = {
            "GRPC_OUTPUT_FORMAT": g.grpc_output_format,
            "USE_AXINFERENCE_NET_OPENCL": g.use_axinference_net_opencl or "",
            "USE_SIMD_DECODE": str(g.use_simd_decode),
            "AXNET_MODEL_PATH": g.axnet_model_path or "",
            "SDK_ROOT": g.sdk_root,
            "AXELERA_FRAMEWORK": g.sdk_root,
            "restart_interval": str(g.restart_interval),
            "timeout": str(g.timeout),
            "flush_thres": str(g.flush_thres),
            "grpc_port_0": str(self.grpc_port),
            "grpc_axnet_config_0": self.grpc_axnet_config,
        }
        if g.pipeline_depth is not None:
            env["pipeline_depth"] = str(g.pipeline_depth)
        if self.taskset_cpus is not None:
            env["taskset_cpus_0"] = self.taskset_cpus
        if self.membind is not None:
            env["membind_0"] = str(self.membind)
        return env


class BuiltinPredicateConfig(BaseModel):
    """A predicate implemented by the server's built-in set.

    The 'type' selects the built-in; any extra keys are accepted and kept as that
    predicate's parameters.
    """

    type: Literal[
        "num_detections_gt", "num_detections_lt", "num_detections_eq",
        "max_score_gt", "max_score_lt",
        "class_present", "meta_key_exists",
        "loop_iter_gte",
        "always_true", "always_false",
        "and", "or", "not",
        "top_class_is", "top_class_score_gt", "top_class_score_lt",
        "kpts_conf_gt",
    ]

    model_config = {"extra": "allow"}


class ExprPredicateConfig(BaseModel):
    """A predicate defined by a restricted Python expression, compiled to C++ by compiler/predicate.py.

    Attributes:
        type (str): Always 'expr'.
        inputs (dict[str, str]): Variable name to helper call, e.g. "num_detections('det')".
        body (str): Expression over the input variables.
    """

    type: Literal["expr"]
    inputs: dict[str, str]
    body: str

    @model_validator(mode="after")
    def _validate_expr(self) -> "ExprPredicateConfig":
        """Require at least one input and a non-blank body."""
        if not self.inputs:
            raise ValueError("ExprPredicateConfig requires at least one input")
        if not self.body.strip():
            raise ValueError("ExprPredicateConfig body must not be empty")
        return self


class PluginPredicateConfig(BaseModel):
    """A predicate loaded from a prebuilt shared library.

    Attributes:
        type (str): Always 'plugin'.
        so_path (str): Path of the .so; environment variables are expanded.
        params (dict[str, Any]): Parameters for the plugin.
    """

    type: Literal["plugin"]
    so_path: str
    params: dict[str, Any] = {}

    @field_validator("so_path")
    @classmethod
    def _expand_so_path(cls, v: str) -> str:
        """Expand environment variables in so_path."""
        return os.path.expandvars(v)


PredicateConfig = Union[BuiltinPredicateConfig, ExprPredicateConfig, PluginPredicateConfig]


class NetConfig(BaseModel):
    """A named model ('nets:' entry) that graph nodes of type 'net' refer to.

    Exactly one of devices or axnet_config must be given. When devices is given, axnet_config
    is derived as 'net-0;devices:<ids>-<cores>'.

    Attributes:
        axnet (str): Path of the compiled .axnet file.
        devices (list[int] | None): Device indices to run on.
        cores (int): Cores per device used when deriving axnet_config. Defaults to 4.
        axnet_config (str | None): Raw axnet config string (mutually exclusive with devices).
        taskset_cpus (str | None): Not read anywhere.
        membind (int | None): Not read anywhere.
        labels_file (Optional[str]): Class labels file.
        meta_key_override (Optional[str]): Replacement for the net's default output meta key.
    """

    axnet: str
    devices: list[int] | None = None
    cores: int = 4
    axnet_config: str | None = None
    taskset_cpus: str | None = None
    membind: int | None = None
    labels_file: Optional[str] = Field(
        default=None,
        description="Path to a .names/.txt class labels file for this net's output classes. "
                    "Supports ${SDK_ROOT}. In a cascade pipeline each net can have its own labels; "
                    "the server uses the first non-None labels_file found across all nets.",
    )
    meta_key_override: Optional[str] = Field(
        default=None,
        description="Rename this net's compiled .axnet's default postprocess meta_key to this "
                    "value (patched into the compiled artifact by server/models/utils/axnet.py after "
                    "regeneration -- see _patch_meta_key_if_requested()). Resolves meta_key "
                    "collisions between nets in the same cascade whose model YAMLs happen to "
                    "share a pipeline stage name (e.g. two nets both defaulting to 'detections') "
                    "-- without renaming one, the second net's output silently clobbers the "
                    "first's in frame->meta, corrupting anything downstream still reading it.",
    )

    @model_validator(mode="after")
    def _resolve_config(self) -> "NetConfig":
        """Validate devices/axnet_config exclusivity, derive axnet_config from devices, and check its syntax.

        Raises:
            ValueError: If both or neither of devices and axnet_config are set, or the config string is malformed.
        """
        has_raw = bool(self.axnet_config)
        has_devs = bool(self.devices)
        if has_raw and has_devs:
            raise ValueError("axnet_config and devices are mutually exclusive")
        if not has_raw and not has_devs:
            raise ValueError("One of devices or axnet_config is required")
        if has_devs and not has_raw:
            idxs = ",".join(str(d) for d in self.devices)
            self.axnet_config = f"net-0;devices:{idxs}-{self.cores}"
        if not _AXNET_CONFIG_RE.match(self.axnet_config):
            raise ValueError(f"Invalid axnet_config: {self.axnet_config!r}")
        return self


class GraphNodeConfig(BaseModel):
    """One node of a pipeline graph.

    A single flat model covers every node type; the validator enforces which optional fields
    each type requires. Fields not relevant to a node's type are not rejected.

    Attributes:
        id (str): Unique node id within the pipeline.
        type (str): Node kind, e.g. 'net', 'filter', 'condition', 'switch', 'fan_out', 'fan_in', 'loop_guard', 'sink'.
        net (str | None): Name of the NetConfig to run (type 'net').
        meta_key (str | None): Meta key read or written by the node.
        next (str | list[str] | None): Successor node id(s); forbidden on sinks, a list of 2+ for fan_out.
        predicate (str | None): Predicate name (condition).
        then (str | None): Target when the predicate is true (condition).
        else_ (str | None): Target when false (condition); YAML key 'else'.
        cases (dict[str, str] | None): Predicate name to target node id (switch).
        default (str | None): Fallback target (switch).
        until (str | None): Exit predicate name (loop_guard).
        continue_to (str | None): Loop-back target (loop_guard).
        exit_to (str | None): Exit target (loop_guard).
        max_iters (int): Iteration cap for loop_guard. Defaults to 3.
        so_path (str | None): Plugin library path (custom).
        gather (str | None): Fan-in merge mode, 'union' or 'none'.
        frames (list[Any] | None): Canned results for mock_net.
        skip_to (str | None): Node to jump to (roi_iter).
        det_meta_key (str | None): Detection meta key (roi_collect).
        cls_meta_key (str | list[str] | None): Classification meta key(s) (roi_collect).
        rename_from (str | None): Source meta key (rename).
        rename_to (str | None): Destination meta key (rename).

    Note:
        The remaining fields (classes, score and size limits, top_k, which, queue depths and
        timeouts, module, fn, crop_padding, ...) are passed through to the server JSON unchanged;
        this model checks only their types.
    """

    id: str
    type: Literal["net", "filter", "fan_out", "fan_in",
                  "condition", "switch", "loop_guard", "custom", "sink",
                  "mock_net", "roi_iter", "roi_collect", "rename"]
    net: str | None = None
    meta_key: str | None = None
    classes: list[int] | None = None
    min_score: float | None = None
    max_score: float | None = None
    min_width: int | None = None
    min_height: int | None = None
    top_k: int | None = None
    which: Literal["highest_score", "center", "all"] | None = "all"
    next: str | list[str] | None = None
    predicate: str | None = None
    then: str | None = None
    else_: str | None = Field(None, alias="else")
    cases: dict[str, str] | None = None
    default: str | None = None
    until: str | None = None
    continue_to: str | None = None
    exit_to: str | None = None
    max_iters: int = 3
    dispatch_queue_depth: int | None = None
    queue_timeout_ms: int | None = None
    queue_depth: int | None = None
    module: str | None = None
    fn: str | None = None
    so_path: str | None = None
    plugin_timeout_ms: int | None = None
    gather: str | None = None
    fanin_timeout_ms: int | None = None
    frames: list[Any] | None = None
    skip_to: str | None = None
    det_meta_key: str | None = None
    cls_meta_key: str | list[str] | None = None
    crop_padding: float = 0.0
    rename_from: str | None = None
    rename_to: str | None = None

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _validate_type_fields(self) -> "GraphNodeConfig":
        """Check the fields each node type requires.

        Raises:
            ValueError: If a field required for the node's type is missing, or a sink has a next field.
        """
        if self.type == "net" and not self.net:
            raise ValueError("type=net requires a 'net' field")
        if self.type == "mock_net":
            if not self.frames:
                raise ValueError("type=mock_net requires a non-empty 'frames' field")
            if not self.meta_key:
                raise ValueError("type=mock_net requires a 'meta_key' field")
        if self.type == "sink" and self.next is not None:
            raise ValueError("type=sink must not have a next field")
        if self.type == "condition":
            if not self.predicate or not self.then or not self.else_:
                raise ValueError("condition node requires predicate, then, and else")
        if self.type == "switch":
            if not self.cases:
                raise ValueError("switch node requires a cases map")
        if self.type == "fan_out":
            if not isinstance(self.next, list) or len(self.next) < 2:
                raise ValueError("fan_out requires next as a list of ≥2 node ids")
        if self.type == "fan_in":
            valid_gather = ("union", "none")
            if self.gather is not None and self.gather not in valid_gather:
                raise ValueError(
                    f"fan_in gather must be one of {valid_gather}, got {self.gather!r}")
        if self.type == "loop_guard":
            if not self.until:
                raise ValueError("loop_guard requires an 'until' predicate")
            if not self.continue_to:
                raise ValueError("loop_guard requires a 'continue_to' node ref")
            if not self.exit_to:
                raise ValueError("loop_guard requires an 'exit_to' node ref")
        if self.type == "custom":
            if not self.so_path:
                raise ValueError("custom node requires a 'so_path' field")
        if self.type == "roi_iter":
            if not self.meta_key:
                raise ValueError("roi_iter requires a 'meta_key' field")
            if not self.skip_to:
                raise ValueError("roi_iter requires a 'skip_to' node ref")
        if self.type == "roi_collect":
            if not self.det_meta_key:
                raise ValueError("roi_collect requires a 'det_meta_key' field")
            if not self.cls_meta_key:
                raise ValueError("roi_collect requires a 'cls_meta_key' field")
        if self.type == "rename":
            if not self.rename_from or not self.rename_to:
                raise ValueError("rename requires both 'rename_from' and 'rename_to' fields")
        return self


def _all_next_refs(node: GraphNodeConfig) -> list[str]:
    """Return every node id a node can transfer control to (next, then, else, continue_to, exit_to, default, skip_to, case targets)."""
    refs: list[str] = []
    if node.next:
        refs += node.next if isinstance(node.next, list) else [node.next]
    for f in [node.then, node.else_, node.continue_to, node.exit_to, node.default,
              node.skip_to]:
        if f:
            refs.append(f)
    if node.cases:
        refs.extend(node.cases.values())
    return refs


def _bfs_reachable(entry: str, nodes: list[GraphNodeConfig]) -> set[str]:
    """Return the ids of nodes reachable from the entry node.

    Raises:
        KeyError: If a reference points at an unknown node id.
    """
    nm = {n.id: n for n in nodes}
    visited: set[str] = set()
    queue = [entry]
    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        queue.extend(_all_next_refs(nm[nid]))
    return visited


def _dfs_detect_unguarded_cycle(nodes: list["GraphNodeConfig"]) -> str | None:
    """Find a cycle in the node graph that does not pass through a loop_guard back-edge.

    The loop_guard to continue_to edges are ignored; any remaining cycle is an error.
    Uses an iterative three-colour depth-first search.

    Returns:
        str | None: An error message describing the cycle, or None if the graph is acyclic.
    """
    guarded_back: set[tuple[str, str]] = set()
    for n in nodes:
        if n.type == "loop_guard" and n.continue_to:
            guarded_back.add((n.id, n.continue_to))

    known: set[str] = {n.id for n in nodes}
    adj: dict[str, list[str]] = {n.id: [] for n in nodes}
    for n in nodes:
        for ref in _all_next_refs(n):
            if (n.id, ref) not in guarded_back and ref in known:
                adj[n.id].append(ref)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {nid: WHITE for nid in adj}

    for start in list(adj):
        if color[start] != WHITE:
            continue
        stack: list[tuple[str, object]] = [(start, iter(adj[start]))]
        color[start] = GRAY
        while stack:
            nid, neighbors = stack[-1]
            try:
                v = next(neighbors)
                vc = color.get(v, WHITE)
                if vc == GRAY:
                    return (
                        f"Cycle detected in pipeline graph (via node '{v}') "
                        "without a loop_guard; add a loop_guard node or fix the topology"
                    )
                if vc == WHITE:
                    color[v] = GRAY
                    stack.append((v, iter(adj[v])))
            except StopIteration:
                color[nid] = BLACK
                stack.pop()
    return None


class PipelineGraphConfig(BaseModel):
    """A pipeline's node graph.

    Attributes:
        entry (str): Id of the first node.
        nodes (list[GraphNodeConfig]): All nodes of the graph.
    """

    entry: str
    nodes: list[GraphNodeConfig]

    @model_validator(mode="after")
    def _validate_graph(self) -> "PipelineGraphConfig":
        """Check entry exists, all references resolve, there is exactly one sink, every node is reachable and no unguarded cycle exists.

        Raises:
            ValueError: On the first violated rule.
        """
        ids = {n.id for n in self.nodes}
        if self.entry not in ids:
            raise ValueError(f"entry '{self.entry}' not in nodes")
        for node in self.nodes:
            for ref in _all_next_refs(node):
                if ref not in ids:
                    raise ValueError(
                        f"Node '{node.id}' has unknown next ref '{ref}'"
                    )
        sinks = [n for n in self.nodes if n.type == "sink"]
        if len(sinks) != 1:
            raise ValueError(f"Exactly one sink required, found {len(sinks)}")
        orphans = ids - _bfs_reachable(self.entry, self.nodes)
        if orphans:
            raise ValueError(f"Orphan nodes (unreachable from entry): {orphans}")
        cycle_err = _dfs_detect_unguarded_cycle(self.nodes)
        if cycle_err:
            raise ValueError(cycle_err)
        return self


class PipelineConfig(BaseModel):
    """One graph pipeline ('pipelines:' entry), served on its own port.

    Attributes:
        id (str): Pipeline identifier.
        interface (Literal['grpc']): Serving protocol; only 'grpc' exists.
        port (int): Server port, 1024-65535.
        taskset_cpus (str | None): CPU list applied with numactl --physcpubind.
        membind (int | None): NUMA node for numactl --membind.
        im_decode_output_format (str): Colour format of decoded frames: BGR, RGBA or I420.
        timeout (int): Per-request timeout in seconds.
        flush_thres (int): Flush threshold in milliseconds.
        imdecode_threads (int | None): Decode thread pool size override.
        imdecode_queue_depth (int | None): Decode frame buffer capacity override.
        imdecode_queue_timeout_ms (int | None): Decode queue backpressure timeout override.
        graph (PipelineGraphConfig): The node graph.
    """

    id: str
    interface: Literal["grpc"] = Field(
        default="grpc",
        description="Server interface protocol this pipeline is served over. "
                    "Only \"grpc\" exists today; kept explicit rather than assumed "
                    "so a future non-gRPC interface doesn't require yet another rename.",
    )
    port: int = Field(..., ge=1024, le=65535, description="Port this pipeline's server listens on")
    taskset_cpus: str | None = Field(
        default=None,
        description="CPU affinity string (e.g. '0-7'); applied as a "
                    "'numactl --physcpubind=...' argv prefix at launch -- "
                    "despite the field name, this never invokes the "
                    "'taskset' binary.",
    )
    membind: int | None = Field(
        default=None,
        description="NUMA node for memory binding (numactl --membind); only "
                    "applied when taskset_cpus is also set.",
    )
    im_decode_output_format: str = Field(
        default="BGR",
        description="BGR | RGBA | I420 — output color format the imdecode worker "
                    "converts each frame to before it enters the pipeline "
                    "(renamed from grpc_output_format -- this isn't a gRPC-specific "
                    "setting, it's the imdecode worker's own output format)",
    )
    timeout: int = Field(default=5, description="Per-request inference timeout (seconds), this pipeline only")
    flush_thres: int = Field(default=4850, description="Pipeline flush threshold (ms), this pipeline only")
    imdecode_threads: int | None = Field(
        default=None,
        description="Decode worker thread pool size override for this pipeline's own "
                    "axinferencenet_grpc process (--imdecode-threads). None keeps "
                    "deployment/launch_remote.py's existing auto-compute (4x this "
                    "pipeline's own pinned core count via taskset_cpus, or the "
                    "binary's own hardware_concurrency() default when unpinned).",
    )
    imdecode_queue_depth: int | None = Field(
        default=None,
        description="Frame buffer capacity override for this pipeline's own "
                    "axinferencenet_grpc process (--imdecode-queue-depth). None "
                    "keeps the binary's own default (1).",
    )
    imdecode_queue_timeout_ms: int | None = Field(
        default=None,
        description="Queue backpressure timeout override (ms) for this pipeline's "
                    "own axinferencenet_grpc process (--imdecode-queue-timeout-ms). "
                    "None keeps the binary's own default (2000ms).",
    )
    graph: PipelineGraphConfig

    @field_validator("im_decode_output_format")
    @classmethod
    def _validate_output_format(cls, v: str) -> str:
        """Check im_decode_output_format against the allowed formats."""
        _check_output_format(v)
        return v


class ServerConfig(BaseModel):
    """Root of the server YAML config.

    Holds the global settings, named nets and predicates, graph pipelines and legacy instances.
    At least one pipeline or instance is required, and ports must be unique across both.

    Attributes:
        global_settings (GlobalSettings): The 'global:' section.
        nets (dict[str, NetConfig]): Named models.
        predicates (dict[str, PredicateConfig]): Named predicates.
        pipelines (list[PipelineConfig]): Graph pipelines.
        instances (list[InstanceConfig]): Legacy instances.
    """

    global_settings: GlobalSettings = Field(..., alias="global")
    nets: dict[str, NetConfig] = {}
    predicates: dict[str, PredicateConfig] = {}
    pipelines: list[PipelineConfig] = []
    instances: list[InstanceConfig] = []

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _cross_validate(self) -> "ServerConfig":
        """Run the checks that span sections.

        Requires at least one pipeline or instance; for instances, contiguous ids from 0 and the
        global fields legacy mode needs; then port uniqueness and net and predicate references.

        Raises:
            ValueError: On the first violated rule.
        """
        if not self.instances and not self.pipelines:
            raise ValueError("At least one of instances: or pipelines: must be non-empty")

        if self.instances:
            ids = [inst.id for inst in self.instances]
            expected = list(range(len(ids)))
            if sorted(ids) != expected:
                raise ValueError(
                    f"instance ids must form a contiguous zero-based sequence "
                    f"(0, 1, 2, ...), got {sorted(ids)}"
                )
            if not self.global_settings.axnet_model_path:
                raise ValueError(
                    "global.axnet_model_path is required when instances: is non-empty"
                )
            if not self.global_settings.use_axinference_net_opencl:
                raise ValueError(
                    "global.use_axinference_net_opencl is required when instances: is non-empty"
                )
            if not self.global_settings.grpc_output_format:
                raise ValueError(
                    "global.grpc_output_format is required when instances: is non-empty"
                )

        self._check_port_uniqueness()
        self._check_net_refs()
        self._check_predicate_refs()
        return self

    def _check_port_uniqueness(self) -> None:
        """Raise ValueError if a port is used by more than one instance or pipeline."""
        ports = [i.grpc_port for i in self.instances] + [p.port for p in self.pipelines]
        seen: set[int] = set()
        for port in ports:
            if port in seen:
                raise ValueError(f"port {port} is used by more than one instance or pipeline")
            seen.add(port)

    def _check_net_refs(self) -> None:
        """Raise ValueError if a pipeline node refers to a net missing from 'nets:'."""
        for pipeline in self.pipelines:
            for node in pipeline.graph.nodes:
                if node.net and node.net not in self.nets:
                    raise ValueError(
                        f"Pipeline '{pipeline.id}' node '{node.id}': "
                        f"undefined net '{node.net}'"
                    )

    def _check_predicate_refs(self) -> None:
        """Raise ValueError if a node's predicate, until or switch case names a predicate missing from 'predicates:'."""
        for pipeline in self.pipelines:
            for node in pipeline.graph.nodes:
                refs = [r for r in [node.predicate, node.until] if r]
                if node.cases:
                    refs.extend(node.cases.keys())
                for ref in refs:
                    if ref not in self.predicates:
                        raise ValueError(
                            f"Pipeline '{pipeline.id}' node '{node.id}': "
                            f"undefined predicate '{ref}'"
                        )


def _expand_vars(obj: object) -> object:
    """Recursively expand environment variables in all strings of a loaded YAML structure."""
    if isinstance(obj, str):
        return os.path.expandvars(obj)
    if isinstance(obj, dict):
        return {k: _expand_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_vars(item) for item in obj]
    return obj


def load_config(path: Union[str, Path]) -> ServerConfig:
    """Load and validate a server config YAML file.

    Environment variables (e.g. ${SDK_ROOT}) in string values are expanded before validation.

    Args:
        path (Union[str, Path]): Path of the YAML file.

    Returns:
        ServerConfig: The validated configuration.

    Raises:
        FileNotFoundError: If the file does not exist.
        pydantic.ValidationError: If the content does not satisfy the schema.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open() as fh:
        raw = yaml.safe_load(fh)
    raw = _expand_vars(raw)
    return ServerConfig.model_validate(raw)
