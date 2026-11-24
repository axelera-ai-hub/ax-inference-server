#!/usr/bin/env python3

"""Patch an installed transformers/AxScript huggingface.py so decode steps are not treated as prefill.

Replaces the cache_position-based prefill check with the adapter's own self._position cursor and resets that cursor at the start of each generate() call.
"""
from __future__ import annotations

import sys
from pathlib import Path

MARKER = "prefill = self._position == 0"

OLD_FORWARD = (
    "            batch, seq = ids.shape\n"
    "            prefill = cache_position is None or int(cache_position[0]) == 0"
)
NEW_FORWARD = (
    "            batch, seq = ids.shape\n"
    "            # `cache_position` is never populated by transformers>=5.x's generate() loop\n"
    "            # for a model that overrides `prepare_inputs_for_generation` -- the only site\n"
    "            # that ever constructs it is gated on `is_remote_code()` and is unreachable\n"
    "            # once a model supplies its own override, as this class does -- so it is\n"
    "            # always None here, misclassifying every decode step as a fresh\n"
    "            # prefill of the whole growing sequence. `self._position` is this adapter's\n"
    "            # own cursor and needs no cooperation from transformers to stay correct, as\n"
    "            # long as it is reset to 0 at the start of every independent `generate()` call\n"
    "            # -- see the reset in this class's own `generate()` override below.\n"
    "            # See patch_axcausallm_cache_position.py for the full story.\n"
    f"            {MARKER}"
)

OLD_PREPARE = (
    "            prefill = cache_position is None or int(cache_position[0]) == 0\n"
    "            inputs = {"
)
NEW_PREPARE = f"            {MARKER}\n            inputs = {{"

OLD_GENERATE_TAIL = (
    "            ids = kwargs.get(\"input_ids\", args[0] if args else kwargs.get(\"inputs\"))\n"
    "            if torch.is_tensor(ids) and ids.dim() > 1 and ids.shape[0] > 1:\n"
    "                raise NotImplementedError(_ONE_SEQUENCE)\n"
    "            return super().generate(*args, **kwargs)"
)
NEW_GENERATE_TAIL = (
    "            ids = kwargs.get(\"input_ids\", args[0] if args else kwargs.get(\"inputs\"))\n"
    "            if torch.is_tensor(ids) and ids.dim() > 1 and ids.shape[0] > 1:\n"
    "                raise NotImplementedError(_ONE_SEQUENCE)\n"
    "            # Every call to `generate()` is an independent request: reset the device-side\n"
    "            # cursor so `forward()`/`prepare_inputs_for_generation()`'s `self._position == 0`\n"
    "            # prefill check is correct even when one loaded instance serves more than one\n"
    "            # request in sequence. See patch_axcausallm_cache_position.py for the full story.\n"
    "            self._position = 0\n"
    "            return super().generate(*args, **kwargs)"
)


def main() -> int:
    """Apply the patch to the file named on the command line.

    Prints ALREADY_PATCHED, PATCHED, or PATCH_TARGET_NOT_FOUND (stderr).

    Returns:
        int: 0 if patched or already patched, 1 if the expected source text was not found, 2 on bad usage.
    """
    if len(sys.argv) != 2:
        print("usage: patch_axcausallm_cache_position.py <path-to-huggingface.py>", file=sys.stderr)
        return 2
    target = Path(sys.argv[1])
    src = target.read_text()

    if src.count(MARKER) == 2 and "self._position = 0\n            return super().generate" in src:
        print("ALREADY_PATCHED")
        return 0

    if OLD_FORWARD not in src or OLD_PREPARE not in src or OLD_GENERATE_TAIL not in src:
        print("PATCH_TARGET_NOT_FOUND", file=sys.stderr)
        return 1

    src = src.replace(OLD_FORWARD, NEW_FORWARD, 1)
    src = src.replace(OLD_PREPARE, NEW_PREPARE, 1)
    src = src.replace(OLD_GENERATE_TAIL, NEW_GENERATE_TAIL, 1)
    target.write_text(src)
    print("PATCHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
