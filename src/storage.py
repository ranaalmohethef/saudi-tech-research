"""Resilient file writing for pipeline outputs.

On Windows an output file is sometimes held for a moment by another process
(file indexer, antivirus, Excel, an editor preview). The write then fails with
``OSError`` - often ``[Errno 22] Invalid argument`` - even though the same
write succeeds a second later.

Every pipeline output therefore goes through these helpers: the data is first
written to a temporary file in the same folder and then moved onto the target
with ``os.replace``, and the whole attempt is retried a few times. The target
file is never left half-written, because the move is atomic.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd

RETRIES = 5
DELAY = 0.5


def _temp_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.tmp")


def _cleanup(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _attempt(path: Path, save, retries: int, delay: float) -> Path:
    """Run ``save(temp_path)`` then atomically move the result onto ``path``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    last_error: OSError | None = None

    for attempt in range(1, retries + 1):
        temp = _temp_path(path)
        try:
            save(temp)
            os.replace(temp, path)
            return path
        except OSError as error:
            last_error = error
            _cleanup(temp)
            if attempt < retries:
                time.sleep(delay * attempt)

    raise OSError(
        f"Could not write {path} after {retries} attempts. "
        f"Close any program that has the file open. Last error: {last_error}"
    )


def write_csv(
    frame: pd.DataFrame,
    path: Path,
    retries: int = RETRIES,
    delay: float = DELAY,
    **kwargs,
) -> Path:
    """Write a DataFrame to CSV, retrying if the target is briefly locked."""
    kwargs.setdefault("index", False)
    return _attempt(Path(path), lambda temp: frame.to_csv(temp, **kwargs), retries, delay)


def write_text(
    text: str,
    path: Path,
    encoding: str = "utf-8",
    retries: int = RETRIES,
    delay: float = DELAY,
) -> Path:
    """Write text to a file, retrying if the target is briefly locked."""
    return _attempt(
        Path(path),
        lambda temp: temp.write_text(text, encoding=encoding),
        retries,
        delay,
    )
