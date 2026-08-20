import time
from typing import Dict, Any, Callable, Awaitable
from actions.circuit_breaker.schemas import CircuitState, CircuitConfig

class CircuitBreakerOpenException(Exception):
    pass

class EnterpriseCircuitBreaker:
    def __init__(self, service_name: str, config: CircuitConfig = CircuitConfig()):
        self.service_name = service_name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.total_requests = 0
        self.last_state_change = time.time()

    def _update_state(self, new_state: CircuitState) -> None:
        self.state = new_state
        self.last_state_change = time.time()
        if new_state == CircuitState.CLOSED:
            self.failure_count = 0
            self.success_count = 0

    def can_execute(self) -> bool:
        now = time.time()
        if self.state == CircuitState.OPEN:
            if now - self.last_state_change >= self.config.recovery_timeout:
                self._update_state(CircuitState.HALF_OPEN)
                return True
            return False
        return True

    async def execute(self, func: Callable[[], Awaitable[Any]]) -> Any:
        self.total_requests += 1
        if not self.can_execute():
            raise CircuitBreakerOpenException(f"Circuit for '{self.service_name}' is OPEN.")

        try:
            result = await func()
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise e

    def on_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.half_open_success_threshold:
                self._update_state(CircuitState.CLOSED)
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def on_failure(self) -> None:
        self.failure_count += 1
        if self.state == CircuitState.HALF_OPEN:
            self._update_state(CircuitState.OPEN)
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self._update_state(CircuitState.OPEN)

    def get_status(self) -> Dict[str, Any]:
        return {
            "service_name": self.service_name,
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "total_requests": self.total_requests
        }
