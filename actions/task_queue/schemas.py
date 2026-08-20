from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class TaskPriority(int, Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 10

class TaskEnqueueRequest(BaseModel):
    task_type: str = Field(..., min_length=1)
    payload: Dict[str, Any] = Field(default_factory=dict)
    priority: TaskPriority = Field(default=TaskPriority.NORMAL)
    max_retries: int = Field(default=2, ge=0)

class TaskResponse(BaseModel):
    task_id: str
    task_type: str
    status: TaskStatus
    priority: TaskPriority
    retries_left: int
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
