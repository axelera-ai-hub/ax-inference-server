# try_push_for

## Summary
`Ax::try_push_for` pushes an item into a `BlockingQueue` and waits up to a timeout for free space.

## Detailed Description
### Behavior
The function waits on the queue's `full_condition` until the queue has space or stops running. It moves the item into the queue only on success. It then notifies one waiting reader.

### Concurrency
The function holds the queue mutex while it checks and pushes. It releases the mutex while it waits.

### Constraints
`item` is an lvalue. The function leaves it unchanged on failure.

## Signature
```cpp
template <typename T>
bool try_push_for(BlockingQueue<T> &q, T &item, std::chrono::milliseconds timeout);
```

## Parameters
| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `q` | `BlockingQueue<T> &` | none | Yes | Destination queue. |
| `item` | `T &` | none | Yes | Item to push. Moved from only on success. |
| `timeout` | `std::chrono::milliseconds` | none | Yes | Maximum time to wait for space. |

## Returns
`bool`. True if the item was pushed. False on timeout or if the queue is stopped.

## Exceptions
The function declares none.

## Edge Cases
- A stopped queue returns false at once.
- A timeout of 0 returns false when the queue is full.

## Related APIs
| API | Relationship |
|---|---|
| [InferenceNode](InferenceNode.md) | Pushes to its queues and to the drop sink. |
| [LoopGuardNode](LoopGuardNode.md) | Pushes to its dispatch queue. |

## Source Reference
`server/include/pipeline/timed_queue_push.h::Ax::try_push_for` (lines 26-38)
