"""health_metrics — opazljivost stanja daemona in agende Rob AI Studio.

Javni API:
    collect_metrics()  -> dict  (strojno berljive metrike)
    summary()          -> str   (kratek tekstovni povzetek)
"""

from .health_metrics import collect_metrics, summary
from .schemas import AgendaCounts, DaemonState, HealthMetrics

__all__ = [
    "collect_metrics",
    "summary",
    "DaemonState",
    "AgendaCounts",
    "HealthMetrics",
]