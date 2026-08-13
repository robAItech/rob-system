from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class EmailRequest(BaseModel):
    to_email: EmailStr
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    is_html: bool = Field(default=False)

class EmailResponse(BaseModel):
    status: str
    provider_used: str
    message_id: Optional[str] = None
