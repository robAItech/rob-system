"""fleet_sync_test — public API.

Re-exports the core logic (``mul`` / ``amul``), the strict Pydantic V2
schemas and the FastAPI router so that ``from fleet_sync_test import mul``
works out of the box.
"""

from .fleet_sync_test import amul, mul
from .main import router
from .schemas import MulRequest, MulResponse

__all__ = ["MulRequest", "MulResponse", "amul", "mul", "router"]
