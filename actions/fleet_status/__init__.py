"""fleet_status — opazljivost flote Rob AI Studio.

Bere `.rob_ai/daemon.json` in `.rob_ai/fleet_workers.json`, jih validira
s Pydantic V2 shemami ter izpostavi strojno (`collect_status`) in
človeško (`summary`) berljiv pogled na floto.
"""

from .fleet_status import DEFAULT_DATA_DIR, collect_status, summary
from .schemas import DaemonStatus, FleetStatus

__all__ = [
    "DEFAULT_DATA_DIR",
    "DaemonStatus",
    "FleetStatus",
    "collect_status",
    "summary",
]