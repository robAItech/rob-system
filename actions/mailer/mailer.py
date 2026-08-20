import asyncio
import uuid
from actions.mailer.schemas import EmailRequest, EmailResponse

class EnterpriseMailer:
    def __init__(self):
        self.primary_fail_sim = False

    async def _send_smtp(self, req: EmailRequest) -> str:
        await asyncio.sleep(0.1) # Simulacija latence
        if self.primary_fail_sim:
            raise ConnectionError("SMTP timeout")
        return f"smtp_{uuid.uuid4().hex[:8]}"

    async def _send_fallback_api(self, req: EmailRequest) -> str:
        await asyncio.sleep(0.1)
        return f"api_{uuid.uuid4().hex[:8]}"

    async def send_email(self, req: EmailRequest) -> EmailResponse:
        try:
            msg_id = await self._send_smtp(req)
            return EmailResponse(status="DELIVERED", provider_used="PRIMARY_SMTP", message_id=msg_id)
        except Exception:
            # Fallback
            msg_id = await self._send_fallback_api(req)
            return EmailResponse(status="DELIVERED", provider_used="FALLBACK_API", message_id=msg_id)
