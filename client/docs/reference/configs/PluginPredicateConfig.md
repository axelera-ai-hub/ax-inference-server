# PluginPredicateConfig

## Overview

`PluginPredicateConfig` is a predicate loaded from a prebuilt shared library.

## Fields

| Field | Type | Default | Required | Constraints | Description |
|---|---|---|---|---|---|
| type | Literal['plugin'] | none | yes | Must be `plugin` | Selects this model. |
| so_path | str | none | yes | Environment variables are expanded | Path of the `.so` file. |
| params | dict[str, Any] | `{}` | no | none | Parameters for the plugin. |

## Validators

| Target | Rule |
|---|---|
| `so_path` | Environment variables are expanded with `os.path.expandvars`. |

## Example

```yaml
predicates:
  custom_check:
    type: plugin
    so_path: ${SDK_ROOT}/plugins/check.so
    params: {threshold: 0.5}
```

## Related

| Page | Relationship |
|---|---|
| [PredicateConfig](PredicateConfig.md) | Union that includes this model. |

## Source Reference

- `client/configs/utils/config_schema.py::PluginPredicateConfig` (lines 249-266)
