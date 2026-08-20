from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class AuditRecordCreate(BaseModel):
    actor: str = Field(..., min_length=1, description="User ID, System Service, or API Key")
    action: str = Field(..., min_length=1, description="Action performed, e.g., UPDATE_BILLING")
    target: str = Field(..., min_length=1, description="Target resource ID")
    payload: Dict[str, Any] = Field(default_factory=dict, description="State changes or parameters")

class AuditRecord(AuditRecordCreate):
    id: str
    timestamp: str
    prev_hash: str
    hash: str

class AuditVerificationResult(BaseModel):
    is_valid: bool
    total_records: int
    broken_at_id: Optional[str] = None
    reason: Optional[str] = None
