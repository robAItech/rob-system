from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

class Role(str, Enum):
    ADMIN = "ADMIN"
    DEVELOPER = "DEVELOPER"
    READ_ONLY = "READ_ONLY"

class ApiKeyCreate(BaseModel):
    client_id: str = Field(..., min_length=1)
    role: Role = Field(default=Role.DEVELOPER)
    ttl_days: int = Field(default=30, ge=1)

class ApiKeyResponse(BaseModel):
    client_id: str
    api_key: str
    role: Role
    created_at: datetime

class TokenVerifyRequest(BaseModel):
    api_key: str
    required_role: Role = Field(default=Role.READ_ONLY)

class VaultEncryptRequest(BaseModel):
    plain_text: str = Field(..., min_length=1)

class VaultDecryptRequest(BaseModel):
    cipher_text: str = Field(..., min_length=1)
