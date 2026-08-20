from pydantic import BaseModel, Field
from typing import Dict

class MetricLabels(BaseModel):
    method: str
    endpoint: str
    status: int

class MetricSnapshot(BaseModel):
    total_requests: int
    error_count: int
    avg_latency_ms: float
