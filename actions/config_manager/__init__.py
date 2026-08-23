"""config_manager package — merged .env-style configuration.

Public API: :class:`ConfigManager` (merge sources, later wins) with
``get(key)`` and ``all()``, plus the reused ``parse_env`` parser and the
Pydantic schemas.
"""

from .config_manager import ConfigManager, EnvSource, merge_env, parse_env
from .schemas import EnvSnapshot, EnvSourceModel

__all__ = [
    "ConfigManager",
    "EnvSource",
    "merge_env",
    "parse_env",
    "EnvSnapshot",
    "EnvSourceModel",
]