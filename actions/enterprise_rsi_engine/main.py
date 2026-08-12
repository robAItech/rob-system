from fastapi import FastAPI, HTTPException
from actions.enterprise_rsi_engine.schemas import AnalyzeRequest, ValidateRequest, OptimizationTarget
from actions.enterprise_rsi_engine.enterprise_rsi_engine import RSIAnalyzer, RSIValidator

app = FastAPI(title="Enterprise RSI Engine", version="1.0.0")

analyzer = RSIAnalyzer()
validator = RSIValidator()


@app.post("/rsi/analyze", response_model=list[OptimizationTarget])
async def analyze(request: AnalyzeRequest):
    """Analyze module code and return optimization targets."""
    try:
        targets = analyzer.find_optimization_targets(request.module_code)
        return targets
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rsi/validate")
async def validate(request: ValidateRequest):
    """Validate behavioral equivalence between original and optimized functions."""
    try:
        is_equivalent = validator.verify_behavioral_equivalence(
            request.original_func,
            request.optimized_func,
            request.func_name,
            request.test_args,
        )
        return {"equivalent": is_equivalent}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))