from typing import Optional, List
from pydantic import BaseModel, Field

class AnalyzeRequest(BaseModel):
    module_code: Optional[str] = Field(default=None, description="Raw python code string")
    target_module_path: Optional[str] = Field(default=None, description="Path to python file")

class FunctionInfo(BaseModel):
    name: str
    args: List[str]
    line_number: int

class ClassInfo(BaseModel):
    name: str
    methods: List[str]
    line_number: int

class AnalyzeResponse(BaseModel):
    success: bool
    functions: List[FunctionInfo]
    classes: List[ClassInfo]
    complexity_score: int
    message: str

class RunLoopRequest(BaseModel):
    target_module_path: str
    max_retries: int = Field(default=5, ge=1, le=10)

class RunLoopResponse(BaseModel):
    success: bool
    attempts_used: int
    message: str
    traceback: str = ""
    modified_files: List[str] = []
