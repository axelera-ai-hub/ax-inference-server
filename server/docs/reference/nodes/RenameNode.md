# RenameNode

## Overview
`Ax::RenameNode` moves a meta entry from one key to another and forwards the frame. The JSON spec uses `type: "rename"` with the fields `rename_from` and `rename_to`.

## Attributes
This class has no public attributes. The constructor takes the meta key to move (`from_key`) and the new key (`to_key`).

## Methods
| Method | Summary | Page |
|---|---|---|
| `process(std::shared_ptr<Frame> frame)` | Moves the entry and forwards the frame to the next node. | This page |

The node forwards the frame unchanged when the source key is absent. It overwrites an existing entry under the destination key.

## Initialization
```cpp
RenameNode(std::string from_key, std::string to_key);
```

## Lifecycle
The node has no threads. Concurrency behavior depends on the underlying runtime.

## Related Classes
| Class | Relationship |
|---|---|
| [AxPipelineNode](AxPipelineNode.md) | Base class. |
| [Frame](Frame.md) | Owns the `meta` map. |

Concept page: [vision/pipeline.md](../../vision/pipeline.md).

## Source Reference
`server/include/nodes/rename.h::Ax::RenameNode` (lines 18-50)
