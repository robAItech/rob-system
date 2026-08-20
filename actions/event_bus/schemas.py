"""Pydantic schemas for the Enterprise Event Bus."""
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class EventMessage(BaseModel):
    """Schema for an event message."""
    payload: Dict[str, Any] = Field(..., description="The event payload")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional metadata")


class PublishRequest(BaseModel):
    """Schema for publishing a message to a topic."""
    payload: Dict[str, Any] = Field(..., description="The event payload")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional metadata")