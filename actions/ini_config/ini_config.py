"""ini_config — INI parsing utilities.

Core domain logic:

* ``parse_ini(text)`` — split INI text into ``{section: {key: value}}``.
* ``read_ini(path)``  — read an INI file from disk and parse it.

The parser is intentionally forgiving (matches common INI dialects):

* comments start with ``#`` or ``;`` (full-line and trailing);
* keys and values are separated by ``=``, ``:`` or whitespace;
* quoted values may contain ``#``/``;`` literally;
* duplicate sections are merged, duplicate keys are overwritten;
* lines before the first section belong to the empty-string section.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

__all__ = ["parse_ini", "read_ini"]


def _parse_value(raw: str) -> str:
    """Strip an inline comment (outside quotes) and surrounding whitespace."""
    in_quote: str | None = None
    for i, ch in enumerate(raw):
        if ch in ("'", '"'):
            if in_quote is None:
                in_quote = ch
            elif in_quote == ch:
                in_quote = None
        elif ch in ("#", ";") and in_quote is None:
            return raw[:i].strip()
    return raw.strip()


def parse_ini(text: str) -> Dict[str, Dict[str, str]]:
    """Parse INI ``text`` into ``{section: {key: value}}``.

    Args:
        text: Raw INI content (may contain leading/trailing whitespace).

    Returns:
        A mapping of section names to key/value mappings. Lines that appear
        before any ``[section]`` header are stored under the ``""`` key.

    Raises:
        TypeError: If ``text`` is not a string.
    """
    if not isinstance(text, str):
        raise TypeError("parse_ini expects a string")

    result: Dict[str, Dict[str, str]] = {}
    current: str = ""

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            result.setdefault(current, {})
            continue

        # Split key/value at the first separator ('=' or ':'), falling back
        # to whitespace separation.
        key: str
        value: str
        sep_index = -1
        for sep in ("=", ":"):
            idx = line.find(sep)
            if idx != -1:
                sep_index = idx
                break
        if sep_index != -1:
            key = line[:sep_index].strip()
            value = _parse_value(line[sep_index + 1 :])
        else:
            parts = line.split(None, 1)
            key = parts[0]
            value = _parse_value(parts[1]) if len(parts) > 1 else ""

        if not key:
            continue
        result.setdefault(current, {})[key] = value

    return result


def read_ini(path: str | os.PathLike[str]) -> Dict[str, Dict[str, str]]:
    """Read the INI file at ``path`` and parse its contents.

    Args:
        path: Filesystem path to the INI file.

    Returns:
        The parsed document as ``{section: {key: value}}``.

    Raises:
        FileNotFoundError: If the file does not exist.
        OSError: On any other read error.
        UnicodeDecodeError: If the file is not valid UTF-8 text.
    """
    file_path = Path(path)
    return parse_ini(file_path.read_text(encoding="utf-8"))