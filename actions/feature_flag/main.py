from fastapi import FastAPI, HTTPException, status
from typing import Dict
from actions.feature_flag.schemas import FeatureFlagCreate, FeatureFlagResponse, EvaluationRequest, EvaluationResponse
from actions.feature_flag.feature_flag import FeatureFlagManager

app = FastAPI(title="Rob AI Studio - Enterprise Feature Flag API")
manager = FeatureFlagManager()

@app.post("/flags", status_code=status.HTTP_201_CREATED, response_model=FeatureFlagResponse)
async def create_or_update_flag(flag: FeatureFlagCreate):
    await manager.upsert_flag(flag)
    return flag

@app.get("/flags/{name}", response_model=FeatureFlagResponse)
async def get_flag(name: str):
    flag = await manager.get_flag(name)
    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    return flag

@app.delete("/flags/{name}")
async def delete_flag(name: str):
    deleted = await manager.delete_flag(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    return {"status": "DELETED", "name": name}

@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_feature(request: EvaluationRequest):
    flag = await manager.get_flag(request.feature_name)
    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")
        
    is_enabled = await manager.evaluate(request.feature_name, request.user_id)
    
    return EvaluationResponse(
        feature_name=request.feature_name,
        user_id=request.user_id,
        is_enabled=is_enabled,
        strategy_applied=flag.strategy.value
    )
