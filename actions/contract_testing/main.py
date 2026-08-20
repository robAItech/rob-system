"""FastAPI application for enterprise contract testing."""

from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from actions.contract_testing.contract_testing import ContractManager
from actions.contract_testing.schemas import (
    ContractGenerateRequest,
    ContractGenerateResponse,
    ContractVerifyRequest,
    ContractVerifyResponse,
    ContractInfo,
)

app = FastAPI(
    title="Enterprise Contract Testing API",
    description="Consumer-Driven Contract (CDC) validation service",
    version="1.0.0",
)

manager = ContractManager()


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}


@app.post("/contracts/generate", response_model=ContractGenerateResponse)
async def generate_contract(request: ContractGenerateRequest) -> ContractGenerateResponse:
    """Generate a new contract.

    Args:
        request: Contract generation request.

    Returns:
        The generated contract.

    Raises:
        HTTPException: If the contract cannot be generated.
    """
    try:
        contract = manager.generate_contract(request.service_name, request.schema)
        return ContractGenerateResponse(**contract)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/contracts/verify", response_model=ContractVerifyResponse)
async def verify_contract(request: ContractVerifyRequest) -> ContractVerifyResponse:
    """Verify a contract between consumer and provider.

    Args:
        request: Contract verification request.

    Returns:
        Verification result.

    Raises:
        HTTPException: If the schemas are invalid.
    """
    try:
        is_valid, errors, warnings = manager.verify_contract(
            request.consumer_schema, request.provider_schema
        )
        return ContractVerifyResponse(valid=is_valid, errors=errors, warnings=warnings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/contracts", response_model=List[ContractInfo])
async def list_contracts() -> List[ContractInfo]:
    """List all stored contracts.

    Returns:
        A list of contracts.
    """
    contracts = manager.list_contracts()
    return [ContractInfo(**contract) for contract in contracts]


@app.get("/contracts/{contract_id}", response_model=ContractInfo)
async def get_contract(contract_id: str) -> ContractInfo:
    """Get a specific contract by ID.

    Args:
        contract_id: The contract ID.

    Returns:
        The contract.

    Raises:
        HTTPException: If the contract is not found.
    """
    try:
        contract = manager.get_contract(contract_id)
        return ContractInfo(**contract)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))