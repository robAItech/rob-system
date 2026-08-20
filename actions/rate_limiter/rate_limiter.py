import time
from collections import defaultdict
from typing import Dict, List, Tuple
from actions.rate_limiter.schemas import RateLimitConfig

class RateLimiter:
    def __init__(self, config: RateLimitConfig = RateLimitConfig()):
        self.config = config
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> Tuple[bool, int, float]:
        now = time.time()
        window_start = now - self.config.window_seconds

        # Očisti zastarele časovne žige znotraj okna
        self.requests[key] = [t for t in self.requests[key] if t > window_start]
        
        current_count = len(self.requests[key])
        
        if current_count < self.config.max_requests:
            self.requests[key].append(now)
            remaining = self.config.max_requests - (current_count + 1)
            return True, remaining, 0.0
        else:
            oldest_request = self.requests[key][0]
            reset_in = max(0.0, oldest_request + self.config.window_seconds - now)
            return False, 0, round(reset_in, 3)
