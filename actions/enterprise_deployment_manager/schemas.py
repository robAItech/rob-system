from pydantic import BaseModel
from typing import List, Dict

class DeploymentResponse(BaseModel):
    status: str
    services_detected: int
    gateway_updated: bool
    docker_exit_code: int
