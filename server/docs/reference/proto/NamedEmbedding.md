# NamedEmbedding

## Overview

`NamedEmbedding` is a feature vector identified by a key. The server sets `key` to the meta key prefix of the embedding.

## Fields

| Field | Number | Type | Label | Description |
|---|---|---|---|---|
| `key` | 1 | `string` | singular | Name of the embedding. |
| `vector` | 2 | `float` | repeated | Vector values. |

## Related Messages

- [Detection](Detection.md)

## Source Reference

- `proto/axinfer/v1/inference.proto::NamedEmbedding` (lines 31-34)
