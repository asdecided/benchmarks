"""Shared file-IO helpers: atomic writes and crash-tolerant JSONL reads.

Results files are the benchmark's only durable output — a torn
`crossover_dataset.json` from a crash mid-write is worse than no file at
all, because downstream tooling (reports, `--augment`) trusts whatever
parses. `atomic_write_text` guarantees a reader sees either the old
content or the new, never a prefix.

`read_jsonl` is the counterpart for the append-and-flush `.partial.jsonl`
sidecars: a crash can truncate only the *final* record mid-line, so that
one is dropped (its cell simply re-runs on resume) while a malformed line
anywhere earlier means real corruption and raises.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Write `text` to `path` atomically (temp file + os.replace).

    The temp file lives in `path.parent` so the replace never crosses a
    filesystem boundary. On any failure the temp file is removed and the
    original `path` (if it existed) is untouched.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fp:
            fp.write(text)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def read_jsonl(path: Path) -> list[dict]:
    """Parse a .jsonl file into a list of records.

    A malformed *final* non-empty line is silently dropped — that is the
    signature of a crash mid-append (the flush never completed), and the
    truncated record's cell is simply re-run. A malformed line anywhere
    else is corruption, not truncation, and raises ValueError.
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    # Trailing blank lines are not records; ignore them when deciding
    # which line counts as "last".
    while lines and not lines[-1].strip():
        lines.pop()
    records: list[dict] = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            if i == len(lines) - 1:
                break  # crash-truncated final record — drop it
            raise ValueError(
                f"{path}: malformed JSONL at line {i + 1} (not the final "
                f"line — corrupt file, not a truncated append): {exc}"
            ) from exc
    return records
