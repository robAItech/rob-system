import asyncio
from typing import Dict
from collections import defaultdict
from actions.enterprise_observability_metrics.schemas import MetricSnapshot

class EnterpriseMetricsRegistry:
    def __init__(self):
        # Format: {(method, endpoint, status): {"count": int, "total_time": float}}
        self.http_metrics: Dict[tuple, Dict[str, float]] = defaultdict(lambda: {"count": 0, "total_time": 0.0})
        self.lock = asyncio.Lock()

    async def record_request(self, method: str, endpoint: str, status: int, duration_sec: float):
        async with self.lock:
            key = (method, endpoint, status)
            self.http_metrics[key]["count"] += 1
            self.http_metrics[key]["total_time"] += duration_sec

    async def generate_prometheus_metrics(self) -> str:
        async with self.lock:
            lines = [
                "# HELP http_requests_total Total number of HTTP requests.",
                "# TYPE http_requests_total counter",
                "# HELP http_request_duration_seconds_sum Total time spent processing HTTP requests.",
                "# TYPE http_request_duration_seconds_sum counter"
            ]
            
            for (method, endpoint, status), data in self.http_metrics.items():
                labels = f'method="{method}",endpoint="{endpoint}",status="{status}"'
                lines.append(f"http_requests_total{{{labels}}} {data['count']}")
                lines.append(f"http_request_duration_seconds_sum{{{labels}}} {data['total_time']:.4f}")
                
            return "\n".join(lines) + "\n"

    async def get_snapshot(self) -> MetricSnapshot:
        async with self.lock:
            total_req = sum(d["count"] for d in self.http_metrics.values())
            total_err = sum(d["count"] for k, d in self.http_metrics.items() if k[2] >= 400)
            total_time = sum(d["total_time"] for d in self.http_metrics.values())
            
            avg_lat = (total_time / total_req * 1000) if total_req > 0 else 0.0
            
            return MetricSnapshot(
                total_requests=total_req,
                error_count=total_err,
                avg_latency_ms=round(avg_lat, 2)
            )
