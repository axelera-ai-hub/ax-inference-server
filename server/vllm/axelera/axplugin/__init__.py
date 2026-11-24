"""vLLM plugin that serves compiled Axelera Metis artifacts.

Exposes register() (platform plugin) and register_model() (general plugin), both wired through entry points in pyproject.toml.
"""

def _runtime_available() -> bool:
    """Return True if the axelera.runtime package can be found without importing it."""
    import importlib.util

    try:
        return importlib.util.find_spec("axelera.runtime") is not None
    except ModuleNotFoundError:
        return False


def register() -> str | None:

    """Return the platform class path for vLLM's "vllm.platform_plugins" entry point.

    Returns:
        str | None: "axplugin.platform.AxeleraPlatform", or None if axelera.runtime is not installed.
    """
    if not _runtime_available():
        return None
    return "axplugin.platform.AxeleraPlatform"


def register_model() -> None:

    """Register the Axelera single-slot models with vLLM ("vllm.general_plugins" entry point).

    For every spec in hf_adapter.SINGLE_SLOT_SPECS, calls its register_auto() and registers the marker model class under the spec's architecture name. Does nothing if axelera.runtime is not installed.
    """
    if not _runtime_available():
        return
    from vllm import ModelRegistry

    from axplugin import hf_adapter

    for single_slot_spec in hf_adapter.SINGLE_SLOT_SPECS.values():
        single_slot_spec.register_auto()
        ModelRegistry.register_model(
            single_slot_spec.architecture, single_slot_spec.marker_model_class
        )
