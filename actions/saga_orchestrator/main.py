"""
FastAPI application for the Enterprise Saga Orchestrator.
"""

import logging
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from actions.saga_orchestrator.saga_orchestrator import (
    SagaManager,
    SagaRequest,
    SagaResponse,
    SagaStepRequest,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Enterprise Saga Orchestrator",
    description="Manages distributed transactions using the Saga pattern",
    version="1.0.0",
)

# Global saga manager instance
saga_manager = SagaManager()


# Register default steps for testing
async def action1(payload: dict) -> dict:
    """Default action 1."""
    return {"status": "success", "step": "action1"}


async def comp1(payload: dict) -> dict:
    """Default compensation 1."""
    return {"compensated": True, "step": "comp1"}


async def action2(payload: dict) -> dict:
    """Default action 2."""
    return {"status": "success", "step": "action2"}


async def comp2(payload: dict) -> dict:
    """Default compensation 2."""
    return {"compensated": True, "step": "comp2"}


async def action3(payload: dict) -> dict:
    """Default action 3."""
    return {"status": "success", "step": "action3"}


async def comp3(payload: dict) -> dict:
    """Default compensation 3."""
    return {"compensated": True, "step": "comp3"}


async def action4(payload: dict) -> dict:
    """Default action 4 that fails."""
    raise Exception("Action failed intentionally")


async def comp4(payload: dict) -> dict:
    """Default compensation 4."""
    return {"compensated": True, "step": "comp4"}


# Register default steps
saga_manager.register_step("step1", action1, comp1)
saga_manager.register_step("step2", action2, comp2)
saga_manager.register_step("step3", action3, comp3)
saga_manager.register_step("step4", action4, comp4)


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/saga/execute")
async def execute_saga(request: SagaRequest) -> SagaResponse:
    """
    Execute a saga with automatic compensation on failure.
    
    Args:
        request: Saga execution request
        
    Returns:
        SagaResponse with execution results
    """
    try:
        result = await saga_manager.execute(request)
        return result.to_response()
    except Exception as e:
        logger.error(f"Error executing saga {request.saga_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/saga/register")
async def register_step(
    name: str,
    action: str,
    compensation: str,
) -> Dict[str, str]:
    """
    Register a new saga step.
    
    Args:
        name: Step name
        action: Action identifier
        compensation: Compensation identifier
        
    Returns:
        Registration confirmation
    """
    # This is a placeholder - in production, you'd map action/compensation
    # strings to actual functions
    async def default_action(payload: dict) -> dict:
        return {"status": "success", "action": action}
    
    async def default_compensation(payload: dict) -> dict:
        return {"compensated": True, "compensation": compensation}
    
    saga_manager.register_step(name, default_action, default_compensation)
    return {"status": "registered", "name": name}


@app.get("/saga/steps")
async def get_registered_steps() -> Dict[str, List[str]]:
    """Get list of registered steps."""
    return {"steps": saga_manager.get_registered_steps()}