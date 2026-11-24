"""Collects non-fatal warnings raised during a release test and prints the final verdict line.

Note:
    Warnings are kept in a module-level list and, if RELEASE_WARN_FILE is set, appended to that file
    as "<RELEASE_TEST_NAME basename>", a tab, then the message.
"""

import os
import time

_WARNINGS: list[str] = []


def warn(msg: str) -> None:
    """Print a timestamped warning, remember it, and append it to RELEASE_WARN_FILE when set."""
    print(f'[{time.strftime("%H:%M:%S")}] WARN: {msg}', flush=True)
    _WARNINGS.append(msg)
    path = os.environ.get('RELEASE_WARN_FILE')
    if path:
        try:
            with open(path, 'a') as f:
                f.write(f'{os.path.basename(os.environ.get("RELEASE_TEST_NAME", "?"))}\t{msg}\n')
        except OSError:
            pass


def warning_count() -> int:
    """Return the number of warnings recorded so far."""
    return len(_WARNINGS)


def verdict(test_name: str) -> None:
    """Print "<test_name>: PASS", with the warning count appended when there were warnings."""
    n = len(_WARNINGS)
    print(f'{test_name}: PASS' + (f' with {n} warning(s)' if n else ''))
