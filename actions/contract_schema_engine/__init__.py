"""
Contract Schema Engine — unified schema registry + contract testing.

Združitev nekdanjih ``schema_registry`` (runtime JSON Schema) in
``contract_testing`` (Consumer-Driven Contract) v en modul z dvema fazama.
"""

from actions.contract_schema_engine.registry import SchemaRegistry
from actions.contract_schema_engine.contracts import ContractManager
from actions.contract_schema_engine.schemas import (
    SchemaRegisterRequest,
    SchemaRegisterResponse,
    SchemaGetResponse,
    SchemaValidateRequest,
    SchemaValidateResponse,
    ContractGenerateRequest,
    ContractGenerateResponse,
    ContractVerifyRequest,
    ContractVerifyResponse,
    ContractInfo,
)

__all__ = [
    "SchemaRegistry",
    "ContractManager",
    "SchemaRegisterRequest",
    "SchemaRegisterResponse",
    "SchemaGetResponse",
    "SchemaValidateRequest",
    "SchemaValidateResponse",
    "ContractGenerateRequest",
    "ContractGenerateResponse",
    "ContractVerifyRequest",
    "ContractVerifyResponse",
    "ContractInfo",
]

__version__ = "1.0.0"
