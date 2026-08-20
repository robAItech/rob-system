"""
Contract Schema Engine — unified FastAPI application.

Združitev nekdanjih modulov v eno storitev z dvema fazama:
- ``SchemaRegistry`` — runtime JSON Schema validacija (registracija + validiranje).
- ``ContractManager`` — Consumer-Driven Contract (CDC) generacija/verifikacija
  (build/CI čas).
"""

from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException

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

app = FastAPI(title="Contract Schema Engine", version="1.0.0")

registry = SchemaRegistry()
manager = ContractManager()


# ── Schema registry (runtime JSON Schema validation) ──────────────────────────

@app.post("/schemas", response_model=SchemaRegisterResponse)
async def register_schema(request: SchemaRegisterRequest) -> SchemaRegisterResponse:
    """Register a new schema."""
    try:
        registry.register(request.name, request.version, request.schema)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return SchemaRegisterResponse(name=request.name, version=request.version)


@app.get("/schemas/{name}/{version}", response_model=SchemaGetResponse)
async def get_schema(name: str, version: int) -> SchemaGetResponse:
    """Retrieve a schema by name and version."""
    schema = registry.get(name, version)
    if schema is None:
        raise HTTPException(status_code=404, detail=f"Schema '{name}' version {version} not found")
    return SchemaGetResponse(name=name, version=version, schema=schema)


@app.post("/validate/{name}/{version}", response_model=SchemaValidateResponse)
async def validate_data(name: str, version: int, request: SchemaValidateRequest) -> SchemaValidateResponse:
    """Validate data against a schema."""
    try:
        errors = registry.validate(name, version, request.data)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return SchemaValidateResponse(valid=len(errors) == 0, errors=errors if errors else None)


# ── Contract testing (CDC generation / verification) ──────────────────────────

@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}


@app.post("/contracts/generate", response_model=ContractGenerateResponse)
async def generate_contract(request: ContractGenerateRequest) -> ContractGenerateResponse:
    """Generate a new contract."""
    try:
        contract = manager.generate_contract(request.service_name, request.schema)
        return ContractGenerateResponse(**contract)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/contracts/verify", response_model=ContractVerifyResponse)
async def verify_contract(request: ContractVerifyRequest) -> ContractVerifyResponse:
    """Verify a contract between consumer and provider."""
    try:
        is_valid, errors, warnings = manager.verify_contract(
            request.consumer_schema, request.provider_schema
        )
        return ContractVerifyResponse(valid=is_valid, errors=errors, warnings=warnings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/contracts", response_model=List[ContractInfo])
async def list_contracts() -> List[ContractInfo]:
    """List all stored contracts."""
    contracts = manager.list_contracts()
    return [ContractInfo(**contract) for contract in contracts]


@app.get("/contracts/{contract_id}", response_model=ContractInfo)
async def get_contract(contract_id: str) -> ContractInfo:
    """Get a specific contract by ID."""
    try:
        contract = manager.get_contract(contract_id)
        return ContractInfo(**contract)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
