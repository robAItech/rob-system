"""
Tests for the Enterprise Saga Orchestrator module.
"""

import asyncio
import pytest
from fastapi.testclient import TestClient

from actions.enterprise_saga_orchestrator.enterprise_saga_orchestrator import (
    SagaManager,
    SagaStep,
    SagaExecutionResult,
    SagaStatus,
    StepStatus,
    StepExecutionResult,
)
from actions.enterprise_saga_orchestrator.schemas import (
    SagaRequest,
    SagaStepRequest,
    SagaResponse,
    StepResponse,
)
from actions.enterprise_saga_orchestrator.main import app


# Test fixtures
@pytest.fixture
def saga_manager_instance():
    """Create a fresh SagaManager instance for each test."""
    manager = SagaManager()
    
    # Register default steps
    async def action1(payload):
        return {"status": "success", "step": "action1"}
    
    async def comp1(payload):
        return {"compensated": True, "step": "comp1"}
    
    async def action2(payload):
        return {"status": "success", "step": "action2"}
    
    async def comp2(payload):
        return {"compensated": True, "step": "comp2"}
    
    async def action3(payload):
        return {"status": "success", "step": "action3"}
    
    async def comp3(payload):
        return {"compensated": True, "step": "comp3"}
    
    async def action4(payload):
        raise Exception("Action failed intentionally")
    
    async def comp4(payload):
        return {"compensated": True, "step": "comp4"}
    
    manager.register_step("step1", action1, comp1)
    manager.register_step("step2", action2, comp2)
    manager.register_step("step3", action3, comp3)
    manager.register_step("step4", action4, comp4)
    
    return manager


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


# Test SagaManager
class TestSagaManager:
    """Tests for SagaManager class."""
    
    @pytest.mark.asyncio
    async def test_successful_execution(self, saga_manager_instance):
        """Test successful saga execution."""
        request = SagaRequest(
            saga_id="test-saga-1",
            steps=[
                SagaStepRequest(name="step1", action="action1", compensation="comp1", payload={}),
                SagaStepRequest(name="step2", action="action2", compensation="comp2", payload={}),
            ],
        )
        
        result = await saga_manager_instance.execute(request)
        
        assert result.status == SagaStatus.COMPLETED
        assert len(result.steps) == 2
        assert all(step.status == StepStatus.COMPLETED for step in result.steps)
        assert result.error is None
    
    @pytest.mark.asyncio
    async def test_failure_with_rollback(self, saga_manager_instance):
        """Test saga failure triggers automatic compensation."""
        request = SagaRequest(
            saga_id="test-saga-2",
            steps=[
                SagaStepRequest(name="step1", action="action1", compensation="comp1", payload={}),
                SagaStepRequest(name="step2", action="action2", compensation="comp2", payload={}),
                SagaStepRequest(name="step3", action="action3", compensation="comp3", payload={}),
            ],
        )
        
        # Make step3 fail by re-registering it with a failing action
        async def failing_action(payload):
            raise Exception("Action failed intentionally")
        
        saga_manager_instance.register_step("step3", failing_action, saga_manager_instance.get_step("step3")["compensation"])
        
        result = await saga_manager_instance.execute(request)
        
        assert result.status == SagaStatus.COMPENSATED
        # 2 completed + 1 failed + 2 compensations (step2 and step1)
        assert len(result.steps) == 5
        assert result.steps[0].status == StepStatus.COMPLETED
        assert result.steps[1].status == StepStatus.COMPLETED
        assert result.steps[2].status == StepStatus.FAILED
        assert result.steps[3].status == StepStatus.COMPENSATED
        assert result.steps[4].status == StepStatus.COMPENSATED
        assert result.error == "Action failed intentionally"
    
    @pytest.mark.asyncio
    async def test_compensation_failure(self, saga_manager_instance):
        """Test scenario where compensation itself fails."""
        request = SagaRequest(
            saga_id="test-saga-3",
            steps=[
                SagaStepRequest(name="step1", action="action1", compensation="comp1", payload={}),
                SagaStepRequest(name="step4", action="action4", compensation="comp4", payload={}),
            ],
        )
        
        # Make compensation for step1 fail
        async def failing_compensation(payload):
            raise Exception("Compensation failed intentionally")
        
        saga_manager_instance.register_step("step1", saga_manager_instance.get_step("step1")["action"], failing_compensation)
        
        result = await saga_manager_instance.execute(request)
        
        assert result.status == SagaStatus.FAILED
        assert len(result.steps) == 3  # step1 completed + step4 failed + step1 compensation failed
        assert result.steps[0].status == StepStatus.COMPLETED
        assert result.steps[1].status == StepStatus.FAILED
        assert result.steps[2].status == StepStatus.COMPENSATION_FAILED
    
    @pytest.mark.asyncio
    async def test_unregistered_step(self, saga_manager_instance):
        """Test execution with unregistered step."""
        request = SagaRequest(
            saga_id="test-saga-4",
            steps=[
                SagaStepRequest(name="unknown", action="unknown", compensation="unknown", payload={}),
            ],
        )
        
        result = await saga_manager_instance.execute(request)
        
        assert result.status == SagaStatus.COMPENSATED
        assert len(result.steps) == 1
        assert result.steps[0].status == StepStatus.FAILED
        assert "not registered" in result.steps[0].error
    
    @pytest.mark.asyncio
    async def test_empty_steps(self, saga_manager_instance):
        """Test execution with no steps."""
        request = SagaRequest(
            saga_id="test-saga-5",
            steps=[],
        )
        
        result = await saga_manager_instance.execute(request)
        
        assert result.status == SagaStatus.COMPLETED
        assert len(result.steps) == 0
    
    def test_register_duplicate_step(self, saga_manager_instance):
        """Test registering a duplicate step (should overwrite)."""
        async def new_action(payload):
            return {"status": "new"}
        
        async def new_compensation(payload):
            return {"compensated": True}
        
        # Should not raise - allows re-registration
        saga_manager_instance.register_step("step1", new_action, new_compensation)
        
        step = saga_manager_instance.get_step("step1")
        assert step is not None
        assert step["action"] == new_action
    
    def test_register_empty_name(self, saga_manager_instance):
        """Test registering step with empty name."""
        async def action(payload):
            return {}
        
        async def compensation(payload):
            return {}
        
        with pytest.raises(ValueError, match="Step name cannot be empty"):
            saga_manager_instance.register_step("", action, compensation)
    
    def test_unregister_step(self, saga_manager_instance):
        """Test unregistering a step."""
        assert saga_manager_instance.unregister_step("step1") is True
        assert saga_manager_instance.unregister_step("nonexistent") is False
        assert saga_manager_instance.get_step("step1") is None
    
    def test_get_step(self, saga_manager_instance):
        """Test getting a step."""
        step = saga_manager_instance.get_step("step1")
        assert step is not None
        assert step["name"] == "step1"
        assert callable(step["action"])
        assert callable(step["compensation"])
        
        assert saga_manager_instance.get_step("nonexistent") is None
    
    @pytest.mark.asyncio
    async def test_async_execution(self, saga_manager_instance):
        """Test async execution method."""
        request = SagaRequest(
            saga_id="test-saga-6",
            steps=[
                SagaStepRequest(name="step1", action="action1", compensation="comp1", payload={}),
            ],
        )
        
        result = await saga_manager_instance.execute_async(request)
        
        assert result.status == SagaStatus.COMPLETED
        assert len(result.steps) == 1
    
    def test_to_response(self):
        """Test conversion to response schema."""
        result = SagaExecutionResult(
            saga_id="test-saga",
            status=SagaStatus.COMPLETED,
            steps=[
                StepExecutionResult(
                    step_name="step1",
                    status=StepStatus.COMPLETED,
                    data={"result": "success"},
                )
            ],
        )
        
        response = result.to_response()
        assert isinstance(response, SagaResponse)
        assert response.saga_id == "test-saga"
        assert response.status == "completed"
        assert len(response.steps) == 1
        assert response.steps[0].step_name == "step1"


# Test API
class TestAPI:
    """Tests for FastAPI endpoints."""
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
    
    def test_execute_saga_success(self, client):
        """Test successful saga execution via API."""
        request = {
            "saga_id": "api-saga-1",
            "steps": [
                {"name": "step1", "action": "action1", "compensation": "comp1", "payload": {}},
                {"name": "step2", "action": "action2", "compensation": "comp2", "payload": {}},
            ],
        }
        
        response = client.post("/saga/execute", json=request)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert len(data["steps"]) == 2
        assert all(step["status"] == "completed" for step in data["steps"])
    
    def test_execute_saga_failure_with_rollback(self, client):
        """Test saga failure with rollback via API."""
        request = {
            "saga_id": "api-saga-2",
            "steps": [
                {"name": "step1", "action": "action1", "compensation": "comp1", "payload": {}},
                {"name": "step4", "action": "action4", "compensation": "comp4", "payload": {}},
            ],
        }
        
        response = client.post("/saga/execute", json=request)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "compensated"
        assert len(data["steps"]) == 3  # step1 completed + step4 failed + step1 compensated
        assert data["steps"][0]["status"] == "completed"
        assert data["steps"][1]["status"] == "failed"
        assert data["steps"][2]["status"] == "compensated"
    
    def test_execute_saga_unregistered_step(self, client):
        """Test saga execution with unregistered step via API."""
        request = {
            "saga_id": "api-saga-3",
            "steps": [
                {"name": "unknown", "action": "unknown", "compensation": "unknown", "payload": {}},
            ],
        }
        
        response = client.post("/saga/execute", json=request)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "compensated"
        assert len(data["steps"]) == 1
        assert data["steps"][0]["status"] == "failed"
        assert "not registered" in data["steps"][0]["error"]
    
    def test_register_step_endpoint(self, client):
        """Test registering a step via API."""
        response = client.post(
            "/saga/register",
            params={"name": "custom_step", "action": "custom_action", "compensation": "custom_comp"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "registered"
        assert response.json()["name"] == "custom_step"
    
    def test_get_registered_steps(self, client):
        """Test getting registered steps via API."""
        response = client.get("/saga/steps")
        assert response.status_code == 200
        data = response.json()
        assert "steps" in data
        assert "step1" in data["steps"]
        assert "step2" in data["steps"]


# Test SagaStep
class TestSagaStep:
    """Tests for SagaStep class."""
    
    def test_step_initialization(self):
        """Test SagaStep initialization."""
        async def action(payload):
            return {}
        
        async def compensation(payload):
            return {}
        
        step = SagaStep("test_step", action, compensation)
        assert step.name == "test_step"
        assert step.action == action
        assert step.compensation == compensation


# Test SagaExecutionResult
class TestSagaExecutionResult:
    """Tests for SagaExecutionResult class."""
    
    def test_result_initialization(self):
        """Test SagaExecutionResult initialization."""
        result = SagaExecutionResult(
            saga_id="test-saga",
            status=SagaStatus.COMPLETED,
            steps=[],
        )
        assert result.saga_id == "test-saga"
        assert result.status == SagaStatus.COMPLETED
        assert result.steps == []
        assert result.error is None
    
    def test_to_response(self):
        """Test conversion to response schema."""
        result = SagaExecutionResult(
            saga_id="test-saga",
            status=SagaStatus.COMPLETED,
            steps=[
                StepExecutionResult(
                    step_name="step1",
                    status=StepStatus.COMPLETED,
                    data={"result": "success"},
                )
            ],
        )
        
        response = result.to_response()
        assert isinstance(response, SagaResponse)
        assert response.saga_id == "test-saga"
        assert response.status == "completed"
        assert len(response.steps) == 1
        assert response.steps[0].step_name == "step1"
        assert response.steps[0].status == "completed"