"""fleet_probe package — javni API.

Re-eksportira javne funkcije modula, da je dostop možen tudi prek
`from actions.fleet_probe import add`.
"""

from .fleet_probe import add

__all__ = ["add"]
