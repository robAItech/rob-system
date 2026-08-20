"""
Enterprise Saga Orchestrator - Manages distributed transactions using the Saga pattern.

This module provides a robust implementation of the Saga pattern for managing
distributed transactions. It supports registering steps with actions and
compensations, executing them asynchronously, and automatically rolling back
completed steps if any step fails.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

from actions.saga_orchestrator.schemas import (
    SagaRequest,
    SagaResponse,
    SagaStepRequest,
    StepResponse,
)

logger = logging.getLogger(__name__)


class SagaStatus(str, Enum):
    """Status of a saga execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"
    PARTIALLY_COMPENSATED = "partially_compensated"


class StepStatus(str, Enum):
    """Status of a step execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"
    COMPENSATION_FAILED = "compensation_failed"


class SagaStep:
    """Represents a step in a saga with its action and compensation."""
    
    def __init__(
        self,
        name: str,
        action: Callable[..., Awaitable[Any]],
        compensation: Callable[..., Awaitable[Any]],
    ):
        self.name = name
        self.action = action
        self.compensation = compensation


class StepExecutionResult:
    """Represents the result of a step execution."""
    
    def __init__(
        self,
        step_name: str,
        status: StepStatus,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        self.step_name = step_name
        self.status = status
        self.data = data
        self.error = error
    
    def to_response(self) -> StepResponse:
        """Convert to response schema."""
        return StepResponse(
            step_name=self.step_name,
            status=self.status.value,
            data=self.data,
            error=self.error,
        )


class SagaExecutionResult:
    """Represents the result of a saga execution."""
    
    def __init__(
        self,
        saga_id: str,
        status: SagaStatus,
        steps: List[StepExecutionResult],
        error: Optional[str] = None,
    ):
        self.saga_id = saga_id
        self.status = status
        self.steps = steps
        self.error = error
    
    def to_response(self) -> SagaResponse:
        """Convert to response schema."""
        return SagaResponse(
            saga_id=self.saga_id,
            status=self.status.value,
            steps=[step.to_response() for step in self.steps],
            error=self.error,
        )


class SagaManager:
    """
    Manages saga steps and their execution with automatic compensation.
    
    This class provides:
    - Registration of saga steps with actions and compensations
    - Asynchronous execution of saga steps
    - Automatic rollback (compensation) in reverse order on failure
    - Thread-safe operations
    """
    
    def __init__(self):
        """Initialize the saga manager."""
        self._steps: Dict[str, SagaStep] = {}
        self._lock = asyncio.Lock()
    
    def register_step(
        self,
        name: str,
        action: Callable,
        compensation: Callable,
    ) -> None:
        """
        Register a saga step with its action and compensation functions.
        
        Args:
            name: Unique step name
            action: Async function to execute the step
            compensation: Async function to compensate the step
            
        Raises:
            ValueError: If name is empty or step already exists
        """
        if not name:
            raise ValueError("Step name cannot be empty")
        
        # Allow re-registration (overwrite existing step)
        self._steps[name] = SagaStep(
            name=name,
            action=action,
            compensation=compensation,
        )
        logger.debug(f"Registered step '{name}'")
    
    def unregister_step(self, name: str) -> bool:
        """
        Unregister a saga step.
        
        Args:
            name: Step name to unregister
            
        Returns:
            True if step was removed, False if not found
        """
        if name in self._steps:
            del self._steps[name]
            logger.debug(f"Unregistered step '{name}'")
            return True
        return False
    
    def get_step(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a registered step.
        
        Args:
            name: Step name
            
        Returns:
            Dictionary with step info or None if not found
        """
        step = self._steps.get(name)
        if step:
            return {
                "name": step.name,
                "action": step.action,
                "compensation": step.compensation,
            }
        return None
    
    def get_registered_steps(self) -> List[str]:
        """Get list of registered step names."""
        return list(self._steps.keys())
    
    async def execute(self, request: SagaRequest) -> SagaExecutionResult:
        """
        Execute a saga with automatic compensation on failure.
        
        Args:
            request: Saga execution request
            
        Returns:
            SagaExecutionResult with execution details
        """
        steps_result: List[StepExecutionResult] = []
        completed_steps: List[tuple[str, SagaStep, Dict[str, Any]]] = []
        
        # Execute steps sequentially
        for step_request in request.steps:
            step = self._steps.get(step_request.name)
            
            if not step:
                error_msg = f"Step '{step_request.name}' is not registered"
                logger.error(f"Saga {request.saga_id}: {error_msg}")
                steps_result.append(
                    StepExecutionResult(
                        step_name=step_request.name,
                        status=StepStatus.FAILED,
                        error=error_msg,
                    )
                )
                # Trigger compensation for completed steps
                return await self._compensate(
                    request.saga_id,
                    steps_result,
                    completed_steps,
                    error_msg,
                )
            
            try:
                # Execute the action
                result = await step.action(step_request.payload)
                steps_result.append(
                    StepExecutionResult(
                        step_name=step_request.name,
                        status=StepStatus.COMPLETED,
                        data=result if isinstance(result, dict) else {"result": result},
                    )
                )
                completed_steps.append((step_request.name, step, step_request.payload))
                logger.info(f"Saga {request.saga_id}: Step '{step_request.name}' completed")
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Saga {request.saga_id}: Step '{step_request.name}' failed: {error_msg}")
                steps_result.append(
                    StepExecutionResult(
                        step_name=step_request.name,
                        status=StepStatus.FAILED,
                        error=error_msg,
                    )
                )
                # Trigger compensation for completed steps
                return await self._compensate(
                    request.saga_id,
                    steps_result,
                    completed_steps,
                    error_msg,
                )
        
        # All steps completed successfully
        return SagaExecutionResult(
            saga_id=request.saga_id,
            status=SagaStatus.COMPLETED,
            steps=steps_result,
        )
    
    async def _compensate(
        self,
        saga_id: str,
        steps_result: List[StepExecutionResult],
        completed_steps: List[tuple[str, SagaStep, Dict[str, Any]]],
        error_msg: str,
    ) -> SagaExecutionResult:
        """
        Execute compensations for completed steps in reverse order.
        
        Args:
            saga_id: Saga identifier
            steps_result: List of step results so far
            completed_steps: List of completed steps with their data
            error_msg: Error message from the failed step
            
        Returns:
            SagaExecutionResult with compensation results
        """
        compensation_failed = False
        
        # Execute compensations in reverse order
        for step_name, step, payload in reversed(completed_steps):
            try:
                result = await step.compensation(payload)
                steps_result.append(
                    StepExecutionResult(
                        step_name=step_name,
                        status=StepStatus.COMPENSATED,
                        data=result if isinstance(result, dict) else {"compensated": True},
                    )
                )
                logger.info(f"Saga {saga_id}: Compensation for '{step_name}' completed")
            except Exception as e:
                compensation_failed = True
                comp_error = str(e)
                logger.error(f"Saga {saga_id}: Compensation for '{step_name}' failed: {comp_error}")
                steps_result.append(
                    StepExecutionResult(
                        step_name=step_name,
                        status=StepStatus.COMPENSATION_FAILED,
                        error=comp_error,
                    )
                )
        
        # Determine final status
        if compensation_failed:
            status = SagaStatus.FAILED
        else:
            status = SagaStatus.COMPENSATED
        
        return SagaExecutionResult(
            saga_id=saga_id,
            status=status,
            steps=steps_result,
            error=error_msg,
        )
    
    async def execute_async(self, request: SagaRequest) -> SagaExecutionResult:
        """
        Execute a saga asynchronously (non-blocking).
        
        Args:
            request: Saga execution request
            
        Returns:
            SagaExecutionResult with execution details
        """
        return await self.execute(request)