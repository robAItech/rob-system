from fastapi import FastAPI
from actions.mailer.schemas import EmailRequest, EmailResponse
from actions.mailer.mailer import EnterpriseMailer

app = FastAPI(title="Rob AI Studio - Enterprise Mailer")
mailer = EnterpriseMailer()

@app.post("/send", response_model=EmailResponse)
async def dispatch_email(req: EmailRequest):
    return await mailer.send_email(req)
