from pydantic import BaseModel
from typing import Any, Dict, List


class OptimizationTarget(BaseModel):
    module_name: str
    function_name: str
    risk_score: float


class AnalyzeRequest(BaseModel):
    module_code: str


class ValidateRequest(BaseModel):
    original_func: str
    optimized_func: str
    func_name: str
    test_args: List[Dict[str, Any]]