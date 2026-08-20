from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class OrchestratorRequest(BaseModel):
    content: str
    content_type: str = Field(..., description="'text', 'audio', ali 'file'")
    metadata: Optional[Dict[str, Any]] = None

class OrchestratorResponse(BaseModel):
    content: str
    provider: str
    latency_ms: float
    is_fallback: bool
