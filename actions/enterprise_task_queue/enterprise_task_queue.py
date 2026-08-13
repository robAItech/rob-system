import asyncio
import uuid
from typing import Dict, List, Optional, Callable, Awaitable, Any
from datetime import datetime
from actions.enterprise_task_queue.schemas import TaskStatus, TaskPriority, TaskEnqueueRequest, TaskResponse

class EnterpriseTaskQueue:
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.handlers: Dict[str, Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]] = {}

    def register_handler(self, task_type: str, handler: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]) -> None:
        self.handlers[task_type] = handler

    def enqueue(self, request: TaskEnqueueRequest) -> TaskResponse:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        
        task_data = {
            "task_id": task_id,
            "task_type": request.task_type,
            "payload": request.payload,
            "priority": request.priority,
            "status": TaskStatus.PENDING,
            "max_retries": request.max_retries,
            "retries_left": request.max_retries,
            "result": None,
            "error": None,
            "created_at": now
        }
        
        self.tasks[task_id] = task_data
        return TaskResponse(**task_data)

    async def process_next(self) -> Optional[TaskResponse]:
        pending = [t for t in self.tasks.values() if t["status"] == TaskStatus.PENDING]
        if not pending:
            return None

        # Razvrsti po prioriteti (višja številka ima prednost)
        pending.sort(key=lambda x: x["priority"].value, reverse=True)
        task = pending[0]
        
        task["status"] = TaskStatus.RUNNING
        handler = self.handlers.get(task["task_type"])

        if not handler:
            task["status"] = TaskStatus.FAILED
            task["error"] = f"No registered handler for task_type '{task['task_type']}'"
            return TaskResponse(**task)

        try:
            res = await handler(task["payload"])
            task["status"] = TaskStatus.SUCCESS
            task["result"] = res
        except Exception as e:
            if task["retries_left"] > 0:
                task["retries_left"] -= 1
                task["status"] = TaskStatus.PENDING
            else:
                task["status"] = TaskStatus.FAILED
                task["error"] = str(e)

        return TaskResponse(**task)

    def get_task(self, task_id: str) -> Optional[TaskResponse]:
        t = self.tasks.get(task_id)
        return TaskResponse(**t) if t else None
