import pytest
import asyncio
from fastapi.testclient import TestClient
from actions.feature_flag.main import app, manager
from actions.feature_flag.schemas import FeatureFlagCreate, FlagStrategy

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_flags():
    manager.flags.clear()

@pytest.mark.asyncio
async def test_feature_flag_strategies():
    m = manager
    
    # 1. BOOLEAN Test
    await m.upsert_flag(FeatureFlagCreate(name="bool_feat", strategy=FlagStrategy.BOOLEAN, enabled=True))
    assert await m.evaluate("bool_feat", "user1") is True
    
    await m.upsert_flag(FeatureFlagCreate(name="bool_feat_off", strategy=FlagStrategy.BOOLEAN, enabled=False))
    assert await m.evaluate("bool_feat_off", "user1") is False

    # 2. TARGETING Test
    await m.upsert_flag(FeatureFlagCreate(
        name="target_feat", 
        strategy=FlagStrategy.TARGETING, 
        enabled=True, 
        targeted_users=["rob", "admin"]
    ))
    assert await m.evaluate("target_feat", "rob") is True
    assert await m.evaluate("target_feat", "guest") is False

    # 3. PERCENTAGE Test (Deterministic)
    await m.upsert_flag(FeatureFlagCreate(
        name="percent_feat", 
        strategy=FlagStrategy.PERCENTAGE, 
        enabled=True, 
        rollout_percentage=50
    ))
    
    # Preverimo, da isti uporabnik dobi enak rezultat dvakrat
    res1 = await m.evaluate("percent_feat", "user_123")
    res2 = await m.evaluate("percent_feat", "user_123")
    assert res1 == res2

def test_fastapi_feature_flag_endpoints():
    # SET
    res_post = client.post("/flags", json={
        "name": "new_ui",
        "strategy": "BOOLEAN",
        "enabled": True
    })
    assert res_post.status_code == 201
    
    # GET
    res_get = client.get("/flags/new_ui")
    assert res_get.status_code == 200
    assert res_get.json()["enabled"] is True
    
    # EVALUATE
    res_eval = client.post("/evaluate", json={
        "feature_name": "new_ui",
        "user_id": "random_user"
    })
    assert res_eval.status_code == 200
    assert res_eval.json()["is_enabled"] is True

    # DELETE
    res_del = client.delete("/flags/new_ui")
    assert res_del.status_code == 200
    
    # EVALUATE 404
    res_eval_404 = client.post("/evaluate", json={
        "feature_name": "new_ui",
        "user_id": "random_user"
    })
    assert res_eval_404.status_code == 404
