from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class FlagStrategy(str, Enum):
    BOOLEAN = "BOOLEAN"
    PERCENTAGE = "PERCENTAGE"
    TARGETING = "TARGETING"

class FeatureFlagCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Unique flag identifier, e.g., new_checkout_v2")
    strategy: FlagStrategy = Field(default=FlagStrategy.BOOLEAN)
    enabled: bool = Field(default=False, description="Global kill switch")
    rollout_percentage: Optional[int] = Field(default=0, ge=0, le=100)
    targeted_users: List[str] = Field(default_factory=list)

class FeatureFlagResponse(FeatureFlagCreate):
    pass

class EvaluationRequest(BaseModel):
    feature_name: str
    user_id: str = Field(..., description="Unique user or session identifier")

class EvaluationResponse(BaseModel):
    feature_name: str
    user_id: str
    is_enabled: bool
    strategy_applied: str
