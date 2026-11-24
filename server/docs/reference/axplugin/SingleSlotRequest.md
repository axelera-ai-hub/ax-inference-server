# SingleSlotRequest

## Overview

Dataclass that `SingleSlotAdapter.admit` returns. It describes the admitted request.

## Attributes

| Attribute | Type | Description |
|---|---|---|
| `slot` | `int` | Batch slot of the request. Always 0. |
| `tokens` | `list[int]` | Tokens produced so far. On admission it holds the first generated token. |

## Methods

This class has no public methods.

## Initialization

Construct it with `SingleSlotRequest(slot, tokens)`. `SingleSlotAdapter.admit` creates it.

## Lifecycle

The instance is a plain value. It is not updated after admission.

## Related Classes

| API | Relationship |
|---|---|
| [SingleSlotAdapter](SingleSlotAdapter.md) | Creates the instance. |
| [AxeleraModelRunner](AxeleraModelRunner.md) | Calls the adapter, which admits each request, during `execute_model`. |

## Source Reference

- `server/vllm/axelera/axplugin/single_slot.py::SingleSlotRequest` (lines 35-44)
