# ArtifactManifest

## Overview

Frozen dataclass that holds the sizing information of a compiled artifact. `read_single_slot_manifest` builds it.

## Attributes

| Attribute | Type | Description |
|---|---|---|
| `context_len` | `int` | Maximum context length the artifact was compiled for. |
| `cache_batch` | `int` | Concurrent sequences supported. Always 1 for single-slot artifacts. |
| `repo_id` | `Optional[str]` | Source Hugging Face repo id, if the manifest records one. |

## Methods

This class has no public methods.

## Initialization

Construct it with `ArtifactManifest(context_len, cache_batch, repo_id)`. Use `read_manifest` or `read_single_slot_manifest` to read one from disk.

## Lifecycle

The instance is immutable.

## Related Classes

| API | Relationship |
|---|---|
| [read_single_slot_manifest](read_single_slot_manifest.md) | Builds the manifest. |
| [read_manifest](read_manifest.md) | Builds the manifest from a vLLM config. |
| [AxeleraPlatform](AxeleraPlatform.md) | Caps the vLLM config to these values. |

## Source Reference

- `server/vllm/axelera/axplugin/hf_adapter.py::ArtifactManifest` (lines 253-264)
