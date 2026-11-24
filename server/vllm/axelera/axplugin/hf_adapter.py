"""Maps compiled Axelera artifacts to the model families, manifests and input builders axplugin supports.

Exposes SINGLE_SLOT_SPECS (keyed by config.json model_type), artifact and manifest resolution, hf_overrides_for() and the adapter loader.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from vllm.config import VllmConfig


def _import_from_spec(spec: str) -> Any:
    """Import an object from a "module.path:Name" spec.

    Args:
        spec (str): Module path and attribute name separated by a colon.
    """
    module_path, _, class_name = spec.partition(":")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _qwen3_single_slot_inputs(
    model: Any, prompt_token_ids: list[int], images: "list[object] | None"
) -> dict[str, Any]:

    """Build the forward() inputs for a qwen3-0.6b text request.

    Args:
        model (Any): The loaded model (not used).
        prompt_token_ids (list[int]): Prompt token ids.
        images (list[object] | None): Must be empty or None; the model is text-only.

    Returns:
        dict[str, Any]: input_ids and an all-ones attention_mask, each of shape (1, n).

    Raises:
        ValueError: If images are supplied.
    """
    import torch

    if images:
        raise ValueError("qwen3-0.6b is text-only; got images for a text request")
    input_ids = torch.tensor([prompt_token_ids])
    attention_mask = torch.ones_like(input_ids)
    return {"input_ids": input_ids, "attention_mask": attention_mask}


def _smolvlm2_single_slot_inputs(
    model: Any, messages: "list[dict] | list[int]", images: "list[object] | None"
) -> dict[str, Any]:

    """Build the forward() inputs for a SmolVLM2 request.

    If messages is empty or does not start with a dict, it is treated as plain prompt token ids. Otherwise each content item of type "image" that has no "image" key receives the next image from images, in order, and the messages are tokenized with the model processor's chat template (generation prompt added).

    Args:
        model (Any): The loaded model; its processor is used for templating.
        messages (list[dict] | list[int]): Chat messages, or prompt token ids.
        images (list[object] | None): Images to place into the chat messages.

    Returns:
        dict[str, Any]: The processor's tensors (e.g. input_ids, attention_mask, pixel values).

    Raises:
        ValueError: If token ids are given together with images.
    """
    if not messages or not isinstance(messages[0], dict):
        import torch

        if images:
            raise ValueError("no chat messages but images were supplied -- unexpected admission payload")
        input_ids = torch.tensor([messages])
        attention_mask = torch.ones_like(input_ids)
        return {"input_ids": input_ids, "attention_mask": attention_mask}

    pending = list(images or [])
    rendered_messages = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            rendered_messages.append(message)
            continue
        new_content = []
        for item in content:
            if item.get("type") == "image" and "image" not in item:
                new_content.append({**item, "image": pending.pop(0)})
            else:
                new_content.append(item)
        rendered_messages.append({**message, "content": new_content})

    return dict(
        model.processor.apply_chat_template(
            rendered_messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
    )


def _register_qwen3_single_slot_auto() -> None:
    """Register the AxScript causal-LM classes with transformers Auto classes."""
    from model_axscript.llm.huggingface import register_auto

    register_auto()


def _register_smolvlm2_auto() -> None:
    """Register the AxScript SmolVLM2 classes with transformers Auto classes."""
    from model_axscript.llm.models.smolvlm2.hf_model import register_auto

    register_auto()


@dataclass(frozen=True)
class SingleSlotSpec:
    """Description of one supported single-slot model family.

    Attributes:
        architecture (str): Architecture name vLLM resolves the model to.
        auto_class (str): Name of the transformers Auto class used to load the artifact.
        register_auto (Callable[[], None]): Registers the model with transformers Auto classes.
        manifest_filename (str): Artifact manifest file holding context_len and repo_id.
        build_inputs (Callable): Builds forward() inputs from (model, prompt data, images).
        marker_model_class (str): "module:Class" spec of the vLLM marker model.
    """

    architecture: str
    auto_class: str
    register_auto: Callable[[], None]
    manifest_filename: str
    build_inputs: Callable[[Any, Any, "list[object] | None"], dict[str, Any]]
    marker_model_class: str


SINGLE_SLOT_SPECS: dict[str, SingleSlotSpec] = {
    "ax_causal_lm": SingleSlotSpec(
        architecture="AxQwen3SingleSlotForCausalLM",
        auto_class="AutoModelForCausalLM",
        register_auto=_register_qwen3_single_slot_auto,
        manifest_filename="pipeline.json",
        build_inputs=_qwen3_single_slot_inputs,
        marker_model_class="axplugin.model:AxSingleSlotTextModel",
    ),
    "ax_smolvlm": SingleSlotSpec(
        architecture="SmolVLMForConditionalGeneration",
        auto_class="AutoModelForImageTextToText",
        register_auto=_register_smolvlm2_auto,
        manifest_filename="vlm.json",
        build_inputs=_smolvlm2_single_slot_inputs,
        marker_model_class="axplugin.model:AxSingleSlotVisionModel",
    ),
}


def _artifact_model_type(artifact_dir: Path) -> str | None:
    """Read model_type from the artifact's config.json.

    Returns:
        str | None: The model_type, or None if config.json is missing or has no model_type.
    """
    config_path = Path(artifact_dir) / "config.json"
    if not config_path.is_file():
        return None
    return json.loads(config_path.read_text()).get("model_type")


def resolve_single_slot_spec(artifact_dir: Path) -> SingleSlotSpec | None:
    """Find the SingleSlotSpec for an artifact directory.

    Args:
        artifact_dir (Path): Compiled artifact directory.

    Returns:
        SingleSlotSpec | None: The spec matching the artifact's model_type, or None if unknown.
    """
    return SINGLE_SLOT_SPECS.get(_artifact_model_type(artifact_dir))


def hf_overrides_for(artifact_dir: Path) -> dict[str, Any]:

    """Compute vLLM hf_overrides for an artifact.

    Args:
        artifact_dir (Path): Compiled artifact directory.

    Returns:
        dict[str, Any]: {"architectures": [<architecture>]} when config.json has no architectures and its model_type is known; otherwise {}.
    """
    config_path = Path(artifact_dir) / "config.json"
    if not config_path.is_file():
        return {}
    data = json.loads(config_path.read_text())
    if data.get("architectures"):
        return {}
    spec = SINGLE_SLOT_SPECS.get(data.get("model_type"))
    if spec is None:
        return {}
    return {"architectures": [spec.architecture]}


def load_single_slot_adapter(spec: SingleSlotSpec, artifact_dir: Path, *, device: Any) -> Any:
    """Load an artifact through transformers and wrap it in a SingleSlotAdapter.

    Args:
        spec (SingleSlotSpec): Spec for the artifact's model family.
        artifact_dir (Path): Compiled artifact directory.
        device (Any): Metis device selector passed to from_pretrained.

    Returns:
        SingleSlotAdapter: Adapter around the loaded model.
    """
    import transformers

    from axplugin.single_slot import SingleSlotAdapter

    spec.register_auto()
    auto_cls = getattr(transformers, spec.auto_class)
    model = auto_cls.from_pretrained(str(artifact_dir), device=device)
    return SingleSlotAdapter(model, build_inputs=spec.build_inputs)


def load_model_class(vllm_config: "VllmConfig") -> Any:
    """Import the vLLM marker model class for the configured artifact.

    Args:
        vllm_config (VllmConfig): vLLM configuration.

    Returns:
        Any: The marker model class.

    Raises:
        ValueError: If no spec matches the artifact.
    """
    artifact_dir = resolve_artifact_dir(vllm_config)
    spec = resolve_single_slot_spec(artifact_dir)
    if spec is None:
        raise ValueError(
            f"no axelera marker model registered for artifact {str(artifact_dir)!r} "
            f"(known model_types: {sorted(SINGLE_SLOT_SPECS)})"
        )
    return _import_from_spec(spec.marker_model_class)


@dataclass(frozen=True)
class ArtifactManifest:
    """Sizing information read from a compiled artifact's manifest.

    Attributes:
        context_len (int): Maximum context length the artifact was compiled for.
        cache_batch (int): Number of concurrent sequences supported; always 1 for single-slot.
        repo_id (str | None): Source Hugging Face repo id, if the manifest records one.
    """
    context_len: int
    cache_batch: int
    repo_id: str | None


def read_single_slot_manifest(artifact_dir: Path, spec: SingleSlotSpec) -> ArtifactManifest:

    """Read the artifact manifest named by the spec.

    Args:
        artifact_dir (Path): Compiled artifact directory.
        spec (SingleSlotSpec): Provides the manifest filename.

    Returns:
        ArtifactManifest: context_len and repo_id from the file; cache_batch fixed to 1.
    """
    manifest_json = json.loads((Path(artifact_dir) / spec.manifest_filename).read_text())
    return ArtifactManifest(
        context_len=int(manifest_json["context_len"]),
        cache_batch=1,
        repo_id=manifest_json.get("repo_id"),
    )


def read_manifest(vllm_config: "VllmConfig") -> ArtifactManifest:

    """Read the manifest of the artifact configured in vllm_config.

    Args:
        vllm_config (VllmConfig): vLLM configuration.

    Returns:
        ArtifactManifest: The artifact's manifest.

    Raises:
        ValueError: If no spec matches the artifact.
    """
    artifact_dir = resolve_artifact_dir(vllm_config)
    spec = resolve_single_slot_spec(artifact_dir)
    if spec is None:
        raise ValueError(
            f"no axelera single-slot spec for artifact {str(artifact_dir)!r} "
            f"(model_type {_artifact_model_type(artifact_dir)!r}; known: {sorted(SINGLE_SLOT_SPECS)})"
        )
    return read_single_slot_manifest(artifact_dir, spec)


def resolve_artifact_dir(vllm_config: "VllmConfig") -> Path:

    """Return the compiled artifact directory.

    Uses additional_config["artifact_dir"] if set, otherwise the model path (model_config.model).

    Args:
        vllm_config (VllmConfig): vLLM configuration.
    """
    additional_config = vllm_config.additional_config or {}
    artifact_dir = additional_config.get("artifact_dir")
    if artifact_dir is not None:
        return Path(artifact_dir)
    return Path(vllm_config.model_config.model)
