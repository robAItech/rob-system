"""zgradi__s7 — povezan sistem: Pydantic V2 sheme, čista async logika, FastAPI.

Pet modulov:
  - schemas.py          : Pydantic V2 sheme s strogimi validatorji
  - zgradi__s7.py       : čista async domenska logika (IntegrationEngine)
  - main.py             : FastAPI router z direktnim JSONResponse 4xx/5xx handlingom
  - __init__.py         : ta paketni vhod
  - test_zgradi__s7.py  : pytest zbirka (100 % pokritost robnih pogojev)
"""

from .schemas import (
    IntegrationIssue,
    IntegrationPhase,
    IntegrationRequest,
    IntegrationResult,
    ModuleSpec,
    ModuleStatus,
)
from .zgradi__s7 import EXPECTED_MODULES, REQUIRED_PHASES, IntegrationEngine
from .main import app

__all__ = [
    "IntegrationEngine",
    "IntegrationIssue",
    "IntegrationPhase",
    "IntegrationRequest",
    "IntegrationResult",
    "ModuleSpec",
    "ModuleStatus",
    "EXPECTED_MODULES",
    "REQUIRED_PHASES",
    "app",
]

__version__ = "1.0.0"
