import pytest
import asyncio
from fastapi.testclient import TestClient
from actions.task_queue.main import app, queue
from actions.task_queue.task_queue import EnterpriseTaskQueue
from actions.task_queue.schemas import TaskEnqueueRequest, TaskPriority, TaskStatus

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_queue():
    queue.tasks.clear()

@pytest.mark.asyncio
async def test_task_queue_priority_and_retry():
    q = EnterpriseTaskQueue()
    
    async def sample_handler(payload: dict) -> dict:
        if payload.get("fail_count", 0) > 0:
            payload["fail_count"] -= 1
            raise ValueError("Task error")
        return {"done": True}

    q.register_handler("test_type", sample_handler)

    # Low vs High Priority
    t_low = q.enqueue(TaskEnqueueRequest(task_type="test_type", payload={}, priority=TaskPriority.LOW))
    t_high = q.enqueue(TaskEnqueueRequest(task_type="test_type", payload={}, priority=TaskPriority.HIGH))

    # High priority is processed first
    processed1 = await q.process_next()
    assert processed1.task_id == t_high.task_id
    assert processed1.status == TaskStatus.SUCCESS

    processed2 = await q.process_next()
    assert processed2.task_id == t_low.task_id
    assert processed2.status == TaskStatus.SUCCESS

def test_fastapi_task_queue_endpoints():
    res = client.post("/tasks/enqueue", json={
        "task_type": "default_echo",
        "payload": {"hello": "world"},
        "priority": 5
    })
    assert res.status_code == 200
    task_id = res.json()["task_id"]

    res_proc = client.post("/tasks/process-next")
    assert res_proc.status_code == 200
    assert res_proc.json()["status"] == "SUCCESS"

    res_get = client.get(f"/tasks/{task_id}")
    assert res_get.status_code == 200
    assert res_get.json()["result"]["processed"] is True
