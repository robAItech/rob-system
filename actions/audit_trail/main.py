from fastapi import FastAPI, HTTPException, status
from typing import List
from actions.audit_trail.schemas import AuditRecordCreate, AuditRecord, AuditVerificationResult
from actions.audit_trail.audit_trail import AuditTrail
from actions.event_bus.event_bus import EventBus

app = FastAPI(title="Rob AI Studio - Enterprise Audit Trail API")
# Audit dogodki gredo prek event_bus-a (asinhrona razpošiljava) v ostale storitve.
audit_bus = EventBus()
audit_trail = AuditTrail(event_bus=audit_bus)

@app.post("/audit", status_code=status.HTTP_201_CREATED, response_model=AuditRecord)
async def log_audit_event(request: AuditRecordCreate):
    return await audit_trail.record_event(request)

@app.get("/audit/verify", response_model=AuditVerificationResult)
async def verify_audit_ledger():
    return await audit_trail.verify_chain()

@app.get("/audit", response_model=List[AuditRecord])
async def get_audit_logs(limit: int = 100):
    # Vrni najnovejše zapise (v produkciji bi tu dodali paginacijo in branje iz diska/DB)
    return audit_trail.chain[-limit:]
