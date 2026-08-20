import hmac
import hashlib
import json
import asyncio
import httpx
import random
from typing import Dict, List, Optional
from datetime import datetime
from actions.api_gateway.schemas import WebhookEndpoint, WebhookEvent, DeliveryResult, DeliveryAttempt, WebhookStatus

class EnterpriseWebhookDispatcher:
    def __init__(self):
        self.endpoints: Dict[str, WebhookEndpoint] = {}
        self.results: Dict[str, DeliveryResult] = {}
        self.timeout = 10.0

    def register_endpoint(self, endpoint: WebhookEndpoint) -> None:
        self.endpoints[endpoint.id] = endpoint

    def _generate_signature(self, secret: str, payload: str, timestamp: str) -> str:
        msg = f"{timestamp}.{payload}".encode("utf-8")
        return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    async def _send_with_retry(self, endpoint: WebhookEndpoint, event: WebhookEvent) -> DeliveryResult:
        result = DeliveryResult(event_id=event.event_id, endpoint_id=endpoint.id, status=WebhookStatus.PENDING)
        payload_str = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
        
        for attempt in range(1, endpoint.max_retries + 2):
            ts = str(int(datetime.utcnow().timestamp()))
            signature = self._generate_signature(endpoint.secret, payload_str, ts)
            
            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Timestamp": ts,
                "X-Webhook-Signature": f"v1={signature}"
            }

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(endpoint.url, content=payload_str, headers=headers)
                    
                    if 200 <= response.status_code < 300:
                        result.attempts.append(DeliveryAttempt(attempt_number=attempt, status_code=response.status_code, success=True, error=None))
                        result.status = WebhookStatus.DELIVERED
                        self.results[f"{event.event_id}_{endpoint.id}"] = result
                        return result
                    else:
                        result.attempts.append(DeliveryAttempt(attempt_number=attempt, status_code=response.status_code, success=False, error=f"HTTP {response.status_code}"))
            except Exception as e:
                result.attempts.append(DeliveryAttempt(attempt_number=attempt, status_code=None, success=False, error=str(e)))

            # Exponential backoff with jitter
            if attempt <= endpoint.max_retries:
                sleep_time = (2 ** attempt) + random.uniform(0.1, 1.0)
                await asyncio.sleep(sleep_time)

        result.status = WebhookStatus.FAILED
        self.results[f"{event.event_id}_{endpoint.id}"] = result
        return result

    async def dispatch(self, endpoint_id: str, event: WebhookEvent) -> Optional[DeliveryResult]:
        endpoint = self.endpoints.get(endpoint_id)
        if not endpoint:
            return None
        return await self._send_with_retry(endpoint, event)
