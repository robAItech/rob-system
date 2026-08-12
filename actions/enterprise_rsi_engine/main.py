import os
from fastapi import FastAPI, HTTPException
from .schemas import AnalyzeRequest, AnalyzeResponse, RunLoopRequest, RunLoopResponse
from .enterprise_rsi_engine import RSIAnalyzer, RSISelfHealingEngine

app = FastAPI(title="Enterprise RSI Engine", version="1.0.0")

@app.post("/rsi/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest):
    code_to_analyze = payload.module_code

    if not code_to_analyze and payload.target_module_path:
        if not os.path.exists(payload.target_module_path):
            raise HTTPException(status_code=400, detail=f"File not found: {payload.target_module_path}")
        with open(payload.target_module_path, "r", encoding="utf-8") as f:
            code_to_analyze = f.read()

    if not code_to_analyze:
        raise HTTPException(
            status_code=400,
            detail="Either 'module_code' or 'target_module_path' must be provided."
        )

    res = RSIAnalyzer.analyze_code(code_to_analyze)
    if not res.success:
        raise HTTPException(status_code=400, detail=res.message)
    return res

@app.post("/rsi/run-loop", response_model=RunLoopResponse)
def run_loop(payload: RunLoopRequest):
    if not os.path.exists(payload.target_module_path):
        raise HTTPException(status_code=404, detail=f"File not found: {payload.target_module_path}")

    res = RSISelfHealingEngine.execute_loop(payload.target_module_path, payload.max_retries)
    return res
