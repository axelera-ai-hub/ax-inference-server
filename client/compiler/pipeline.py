#!/usr/bin/env python3
"""Compile a server YAML config into per-pipeline JSON specs for the pipeline server.

Usage: pipeline.py <config.yaml> <output_dir>
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "configs" / "utils"))

from config_schema import (
    ExprPredicateConfig, GraphNodeConfig, PipelineConfig, ServerConfig, load_config,
)

_SUPPORTED_TYPES = {
    "net", "filter", "condition", "switch",
    "fan_out", "fan_in", "loop_guard", "custom", "sink", "mock_net",
    "roi_iter", "roi_collect", "rename",
}


@dataclass
class ProcessSpec:
    """Launch description for one compiled pipeline server process.

    Attributes:
        pipeline_id (str): Pipeline id from the config.
        port (int): Port the pipeline's server listens on.
        pipeline_json_path (str): Path of the generated pipeline JSON file.
        taskset_cpus (Optional[str]): CPU list for taskset pinning, or None for no pinning.
        membind (Optional[int]): NUMA node for memory binding, or None.
        env (dict[str, str]): Extra environment variables for the process.
    """

    pipeline_id: str
    port: int
    pipeline_json_path: str
    taskset_cpus: Optional[str]
    membind: Optional[int]
    env: dict[str, str]


_ROLE_BY_DECODER_NAME: dict[str, str] = {
    "CocoBodyKeypointsMeta": "keypoints",
    "FaceLandmarkLocalizationMeta": "face",
}


def _read_axnet_postprocess_options(axnet_path: str) -> list[str]:
    """Return the 'postprocess*_options=' lines of an .axnet file, or [] if the file does not exist."""
    path = Path(axnet_path)
    if not path.exists():
        return []
    return [line for line in path.read_text().splitlines()
            if line.startswith("postprocess") and "_options=" in line]


def _effective_meta_key(net_cfg, axnet_path: str) -> Optional[str]:
    """Return the meta key a net publishes its results under.

    The config's meta_key_override wins; otherwise the first 'meta_key:' option found in the
    .axnet postprocess lines is used. Returns None if neither is set.
    """
    if net_cfg.meta_key_override:
        return net_cfg.meta_key_override
    for line in _read_axnet_postprocess_options(axnet_path):
        if "meta_key:" not in line:
            continue
        return line.partition("meta_key:")[2].partition(";")[0]
    return None


def _detect_net_role(axnet_path: str) -> Optional[str]:
    """Infer a net's role from the decoder named in its .axnet postprocess options.

    Returns:
        Optional[str]: 'keypoints' or 'face' for known decoders, otherwise None.
    """
    for line in _read_axnet_postprocess_options(axnet_path):
        if "decoder_name:" not in line:
            continue
        decoder_name = line.partition("decoder_name:")[2].partition(";")[0]
        return _ROLE_BY_DECODER_NAME.get(decoder_name)
    return None


class PipelineCompiler:
    """Compiles a ServerConfig into per-pipeline JSON specs and process launch descriptions.

    Writes one pipeline_<index>.json per pipeline into the output directory; expression
    predicates are compiled to shared libraries there as well.
    """

    def __init__(self, config: ServerConfig, output_dir: Path) -> None:
        """Store the config and create the output directory if needed.

        Args:
            config (ServerConfig): Validated server configuration.
            output_dir (Path): Directory for generated JSON files and predicate libraries.
        """
        self._cfg = config
        self._out = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

    def compile_all(self) -> list[ProcessSpec]:
        """Compile every pipeline in the config.

        Returns:
            list[ProcessSpec]: One entry per pipeline, in config order.

        Raises:
            NotImplementedError: If a pipeline uses an unsupported node type.
        """
        return [self._compile(i, p) for i, p in enumerate(self._cfg.pipelines)]

    def _compile(self, index: int, pipeline: PipelineConfig) -> ProcessSpec:
        """Validate one pipeline, write its JSON spec to pipeline_<index>.json and build its ProcessSpec."""
        self._check_supported(pipeline)
        spec = self._build_spec(pipeline)
        path = self._out / f"pipeline_{index}.json"
        path.write_text(json.dumps(spec, indent=2))
        return ProcessSpec(
            pipeline_id=pipeline.id,
            port=pipeline.port,
            pipeline_json_path=str(path),
            taskset_cpus=pipeline.taskset_cpus,
            membind=pipeline.membind,
            env=self._env(pipeline),
        )

    def _check_supported(self, pipeline: PipelineConfig) -> None:
        """Reject pipelines containing node types outside the supported set.

        Raises:
            NotImplementedError: If a node's type is not in _SUPPORTED_TYPES.
        """
        for node in pipeline.graph.nodes:
            if node.type not in _SUPPORTED_TYPES:
                feature = "a future feature"
                raise NotImplementedError(
                    f"Node type '{node.type}' in pipeline '{pipeline.id}' "
                    f"is not yet implemented. [{node.type}: {feature}]"
                )

    def _build_spec(self, pipeline: PipelineConfig) -> dict:
        """Build the pipeline JSON document.

        Contains the entry node, a 'global' block (timeouts, pipeline depth defaulting to 13, restart
        and watchdog settings, plus optional queue and imdecode settings when configured), the nets
        and predicates the graph references, and the node list.
        """
        g = self._cfg.global_settings
        referenced_nets = {n.net for n in pipeline.graph.nodes if n.net}
        pred_refs = self._collect_referenced_predicates(pipeline)
        global_block = {
            "timeout_s": pipeline.timeout,
            "pipeline_depth": g.pipeline_depth if g.pipeline_depth is not None else 13,
            "im_decode_output_format": pipeline.im_decode_output_format,
            "restart_interval_s": g.restart_interval,
            "watchdog_timeout_ms": g.watchdog_timeout_ms,
        }
        if g.result_queue_depth is not None:
            global_block["result_queue_depth"] = g.result_queue_depth
        if pipeline.imdecode_threads is not None:
            global_block["imdecode_threads"] = pipeline.imdecode_threads
        if pipeline.imdecode_queue_depth is not None:
            global_block["imdecode_queue_depth"] = pipeline.imdecode_queue_depth
        if pipeline.imdecode_queue_timeout_ms is not None:
            global_block["imdecode_queue_timeout_ms"] = pipeline.imdecode_queue_timeout_ms
        return {
            "pipeline_id": pipeline.id,
            "entry": pipeline.graph.entry,
            "global": global_block,
            "nets": {
                name: self._net_json(name)
                for name in referenced_nets
            },
            "predicates": {
                name: self._predicate_json(name)
                for name in pred_refs
            },
            "nodes": [self._node_dict(n, pipeline) for n in pipeline.graph.nodes],
        }

    def _net_json(self, name: str) -> dict:
        """Build the JSON entry for one net: axnet paths plus the detected meta_key and role when available."""
        net_cfg = self._cfg.nets[name]
        d = {
            "axnet_path": net_cfg.axnet,
            "axnet_config": net_cfg.axnet_config,
        }
        meta_key = _effective_meta_key(net_cfg, net_cfg.axnet)
        if meta_key:
            d["meta_key"] = meta_key
        role = _detect_net_role(net_cfg.axnet)
        if role:
            d["role"] = role
        return d

    def _predicate_json(self, name: str) -> dict:
        """Build the JSON entry for one predicate.

        Expression predicates are compiled to a shared library and referenced as a 'plugin' entry
        with its so_path; other predicate configs are dumped as-is.
        """
        cfg = self._cfg.predicates[name]
        if isinstance(cfg, ExprPredicateConfig):
            from predicate import PredicateCompiler
            so_path = PredicateCompiler(
                name, cfg, self._out, self._cfg.global_settings.sdk_root
            ).compile()
            return {"type": "plugin", "so_path": str(so_path)}
        return cfg.model_dump()

    def _collect_referenced_predicates(self, pipeline: PipelineConfig) -> set[str]:
        """Return the predicate names used by nodes via predicate, until, or the keys of cases."""
        refs: set[str] = set()
        for node in pipeline.graph.nodes:
            for ref in [node.predicate, node.until]:
                if ref:
                    refs.add(ref)
            if node.cases:
                refs.update(node.cases.keys())
        return refs

    def _fanin_num_branches(self, fanin_id: str, pipeline: PipelineConfig) -> int:
        """Count the nodes whose 'next' includes the given fan-in node id."""
        count = 0
        for node in pipeline.graph.nodes:
            nexts: list[str] = (
                node.next if isinstance(node.next, list)
                else ([node.next] if node.next else [])
            )
            if fanin_id in nexts:
                count += 1
        return count

    def _node_dict(self, node: GraphNodeConfig,
                   pipeline: PipelineConfig | None = None) -> dict:
        """Serialise a graph node to a dict, omitting unset fields.

        A string 'next' becomes a one-element list. For fan_in nodes, missing num_branches,
        fanin_timeout_ms (2 * flush_thres) and gather ('union') are filled in when a pipeline is given.
        """
        d = node.model_dump(exclude_none=True, by_alias=True)
        if "next" in d and isinstance(d["next"], str):
            d["next"] = [d["next"]]
        if node.type == "fan_in" and pipeline is not None:
            if "num_branches" not in d:
                d["num_branches"] = self._fanin_num_branches(node.id, pipeline)
            if "fanin_timeout_ms" not in d:
                d["fanin_timeout_ms"] = pipeline.flush_thres * 2
            if "gather" not in d:
                d["gather"] = "union"
        return d

    def _env(self, pipeline: PipelineConfig) -> dict[str, str]:
        """Build the environment for a pipeline process: AXELERA_FRAMEWORK (SDK root) and GRPC_OUTPUT_FORMAT."""
        g = self._cfg.global_settings
        return {
            "AXELERA_FRAMEWORK": g.sdk_root,
            "GRPC_OUTPUT_FORMAT": pipeline.im_decode_output_format,
        }


def main() -> None:
    """Compile a config from the command line and print one 'id<TAB>port<TAB>json_path' line per pipeline.

    Exits with status 1 and a usage message unless exactly two arguments are given.
    """
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <config.yaml> <output_dir>", file=sys.stderr)
        sys.exit(1)

    config_path, output_dir = sys.argv[1], Path(sys.argv[2])
    cfg = load_config(config_path)
    specs = PipelineCompiler(cfg, output_dir=output_dir).compile_all()
    for spec in specs:
        print(f"{spec.pipeline_id}\t{spec.port}\t{spec.pipeline_json_path}")


if __name__ == "__main__":
    main()
