from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Optional

class CacheStats(BaseModel):
    model_config = ConfigDict(frozen=True)
    hits: int
    misses: int
    evictions: int
    current_size: int
    max_size: int

class CacheSetRequest(BaseModel):
    key: str = Field(..., min_length=1)
    value: Any
    ttl_seconds: Optional[float] = Field(default=None, gt=0.0)

class CacheResponse(BaseModel):
    key: str
    value: Optional[Any] = None
    found: bool
