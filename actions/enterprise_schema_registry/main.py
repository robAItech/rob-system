# actions/enterprise_schema_registry/main.py
from fastapi import FastAPI, HTTPException
from typing import Dict, Any

from actions.enterprise_schema_registry.enterprise_schema_registry import SchemaRegistry
from actions.enterprise_schema_registry.schemas import (
    SchemaRegisterRequest,
    SchemaRegisterResponse,
    SchemaGetResponse,
    SchemaValidateRequest,
    SchemaValidateResponse,
)

app = FastAPI(title="Enterprise Schema Registry", version="1.0.0")

# Initialize the schema registry
registry = SchemaRegistry()


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