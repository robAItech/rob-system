from fastapi import FastAPI, HTTPException, status
from typing import Optional
from actions.task_queue.schemas import TaskEnqueueRequest, TaskResponse
from actions.task_queue.task_queue import EnterpriseTaskQueue

app = FastAPI(title="Rob AI Studio - Enterprise Task Queue API")
queue = EnterpriseTaskQueue()

async def default_echo_handler(payload: dict) -> dict:
    if payload.get("should_fail"):
        raise ValueError("Simulated task processing failure")
    return {"processed": True, "data": payload}

queue.register_handler("default_echo", default_echo_handler)

@app.post("/tasks/enqueue", response_model=TaskResponse)
async def enqueue_task(request: TaskEnqueueRequest):
    return queue.enqueue(request)

@app.post("/tasks/process-next", response_model=Optional[TaskResponse])
async def process_task():
    return await queue.process_next()

@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str):
    res = queue.get_task(task_id)
    if not res:
        raise HTTPException(status_code=404, detail="Task not found")
    return res
