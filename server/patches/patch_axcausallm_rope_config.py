#!/usr/bin/env python3

"""Patch an AxScript huggingface.py so AxCausalLMConfig sets max_position_embeddings before RoPE standardization.

Adds a __post_init__ that assigns it from the leftover kwargs, avoiding an AttributeError in transformers' RoPE parameter conversion.
"""
from __future__ import annotations

import sys
from pathlib import Path

MARKER = 'self.max_position_embeddings = kwargs["max_position_embeddings"]'

OLD_CLASS = (
    "    class AxCausalLMConfig(PretrainedConfig):\n"
    '        """A compiled AxScript causal LM: the checkpoint\'s shape, under our own type."""\n'
    "\n"
    "        model_type = MODEL_TYPE"
)
NEW_CLASS = (
    "    class AxCausalLMConfig(PretrainedConfig):\n"
    '        """A compiled AxScript causal LM: the checkpoint\'s shape, under our own type."""\n'
    "\n"
    "        model_type = MODEL_TYPE\n"
    "\n"
    "        def __post_init__(self, **kwargs):\n"
    "            # transformers>=4.57's RoPE standardization (__post_init__ ->\n"
    "            # convert_rope_params_to_dict -> standardize_rope_params) reads\n"
    "            # self.max_position_embeddings unconditionally whenever both rope_scaling\n"
    "            # and rope_theta are set (true for every Llama3-family checkpoint using\n"
    "            # long-context RoPE scaling). This bare config class declares no dataclass\n"
    "            # fields of its own, so the generated __init__ never assigns\n"
    "            # max_position_embeddings as a real instance attribute before calling here,\n"
    "            # crashing with: AttributeError: 'AxCausalLMConfig' object has no attribute\n"
    "            # 'max_position_embeddings'. Set it from the leftover kwargs ourselves,\n"
    "            # before delegating, so the inherited RoPE standardization has what it\n"
    "            # expects -- rope_scaling/rope_theta are untouched, so long-context scaling\n"
    "            # still applies exactly as the checkpoint declares it. See\n"
    "            # patch_axcausallm_rope_config.py for the full story.\n"
    "            if \"max_position_embeddings\" in kwargs and not hasattr(self, \"max_position_embeddings\"):\n"
    f"                {MARKER}\n"
    "            super().__post_init__(**kwargs)"
)


def main() -> int:
    """Apply the patch to the file named on the command line.

    Prints ALREADY_PATCHED, PATCHED, or PATCH_TARGET_NOT_FOUND (stderr).

    Returns:
        int: 0 if patched or already patched, 1 if the expected source text was not found, 2 on bad usage.
    """
    if len(sys.argv) != 2:
        print("usage: patch_axcausallm_rope_config.py <path-to-huggingface.py>", file=sys.stderr)
        return 2
    target = Path(sys.argv[1])
    src = target.read_text()

    if MARKER in src:
        print("ALREADY_PATCHED")
        return 0

    if OLD_CLASS not in src:
        print("PATCH_TARGET_NOT_FOUND", file=sys.stderr)
        return 1

    src = src.replace(OLD_CLASS, NEW_CLASS, 1)
    target.write_text(src)
    print("PATCHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
