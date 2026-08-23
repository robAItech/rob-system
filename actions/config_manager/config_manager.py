"""config_manager — merge multiple .env-style sources into one view.

The module reuses ``actions.env_config.parse_env`` for parsing raw .env
content and provides :class:`ConfigManager`, which merges any number of
.env-style sources (raw text, file paths or already-parsed mappings) with
a "later source wins" policy, plus ``get(key)`` and ``all()`` accessors.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Mapping, Optional, Union

try:
    from actions.env_config import parse_env
except ImportError:  # pragma: no cover - fallback for standalone runs
    try:
        from actions.env_config.env_config import parse_env
    except ImportError:  # pragma: no cover - fallback for standalone runs

        def parse_env(text: str) -> Dict[str, str]:
            """Minimal .env parser used only when actions.env_config is absent."""
            result: Dict[str, str] = {}
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if not key:
                    continue
                result[key] = value.strip().strip('"').strip("'")
            return result


EnvSource = Union[str, os.PathLike, Mapping[str, str]]


def _parse_source(source: EnvSource) -> Dict[str, str]:
    """Normalise one user-supplied source into a {key: value} mapping."""
    if isinstance(source, Mapping):
        return {str(k): str(v) for k, v in source.items()}
    if isinstance(source, os.PathLike):
        source = os.fspath(source)
    if not isinstance(source, str):
        raise TypeError(
            f"env source must be str, Path or Mapping, got {type(source).__name__}"
        )
    # A string that names an existing file is treated as a .env file path;
    # anything else is treated as raw .env content.
    if Path(source).is_file():
        text = Path(source).read_text(encoding="utf-8")
    else:
        text = source
    return dict(parse_env(text))


class ConfigManager:
    """Merged view over several .env-style sources (later sources win).

    Parameters
    ----------
    *sources:
        Raw .env content strings, paths to .env files, or mappings
        (e.g. already parsed dicts). Sources are merged left to right;
        keys from later sources override earlier ones.
    """

    def __init__(self, *sources: EnvSource) -> None:
        self._data: Dict[str, str] = {}
        for source in sources:
            self._data.update(_parse_source(source))

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Return the value for ``key`` or ``default`` (None) when missing."""
        return self._data.get(key, default)

    def all(self) -> Dict[str, str]:
        """Return a shallow copy of the fully merged configuration."""
        return dict(self._data)

    def __getitem__(self, key: str) -> str:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def items(self):
        return self._data.items()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"ConfigManager({self._data!r})"


def merge_env(*sources: EnvSource) -> Dict[str, str]:
    """Convenience helper: merge ``sources`` and return the combined mapping."""
    return ConfigManager(*sources).all()


__all__ = ["ConfigManager", "merge_env", "parse_env", "EnvSource"]