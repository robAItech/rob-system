"""
Pydantic schemas for the Enterprise Saga Orchestrator module.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SagaStepRequest(BaseModel):
    """Request schema for a saga step."""
    name: str = Field(..., description="Step name")
    action: str = Field(..., description="Action identifier")
    compensation: str = Field(..., description="Compensation identifier")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Step payload")


class SagaRequest(BaseModel):
    """Request schema for saga execution."""
    saga_id: str = Field(..., description="Saga identifier")
    steps: List[SagaStepRequest] = Field(
        default_factory=list,
        description="List of steps to execute",
    )


class StepResponse(BaseModel):
    """Response schema for a step execution result."""
    step_name: str
    status: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class SagaResponse(BaseModel):
    """Response schema for saga execution result."""
    saga_id: str
    status: str
    steps: List[StepResponse]
    error: Optional[str] = None