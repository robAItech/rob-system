"""actions.config_loader — konsolidiran modul za .env in INI razčlenjevanje.

Javni API (po direktivi):
  * ``parse_env``, ``load_env`` — .env razčlenjevanje
  * ``parse_ini``, ``read_ini`` — INI razčlenjevanje
  * ``ConfigManager``, ``merge_env`` — združevanje virov ('later wins')
"""

from .config_loader import (ConfigManager, load_env, merge_env, parse_env,
                            parse_ini, read_ini)

__all__ = [
    "ConfigManager",
    "load_env",
    "merge_env",
    "parse_env",
    "parse_ini",
    "read_ini",
]