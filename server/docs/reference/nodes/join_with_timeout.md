# join_with_timeout

## Summary
`Ax::join_with_timeout` joins a `std::thread` and waits at most a timeout. It abandons the thread if the timeout expires.

## Detailed Description
### Behavior
The function moves the target thread into a detached helper thread. The helper performs the blocking join and sets `JoinState::done`. The caller waits on `JoinState::cv` for the timeout. On timeout, the helper and the target keep running and the function logs a message to the `PIPELINE` log. `JoinState` holds `m` (mutex), `cv` (condition variable) and `done` (bool).

### Concurrency
The function leaves `target` non-joinable. A helper thread that never finishes leaks.

### Constraints
The function returns true at once if `target` is not joinable.

## Signature
```cpp
inline bool join_with_timeout(std::thread &target, std::chrono::milliseconds timeout,
                              const std::string &label);
```

## Parameters
| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `target` | `std::thread &` | none | Yes | Thread to join. |
| `timeout` | `std::chrono::milliseconds` | none | Yes | Maximum time to wait. |
| `label` | `const std::string &` | none | Yes | Name used in the log message on timeout. |

## Returns
`bool`. True if the thread was joined or was not joinable. False on timeout.

## Exceptions
The function declares none.

## Edge Cases
- A timeout leaves the thread running after shutdown continues.
- `InferenceNode::stop()` and `LoopGuardNode::stop()` call this function.

## Related APIs
| API | Relationship |
|---|---|
| [InferenceNode](InferenceNode.md) | Joins its push and drain threads. |
| [LoopGuardNode](LoopGuardNode.md) | Joins its dispatch thread. |

## Source Reference
`server/include/pipeline/join_with_timeout.h::Ax::join_with_timeout` (lines 47-72), `server/include/pipeline/join_with_timeout.h::Ax::JoinState` (lines 25-29)
