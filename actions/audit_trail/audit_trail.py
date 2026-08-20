import hashlib
import json
import asyncio
from datetime import datetime
from typing import List
from actions.audit_trail.schemas import AuditRecordCreate, AuditRecord, AuditVerificationResult

class EnterpriseAuditTrail:
    def __init__(self):
        self.chain: List[AuditRecord] = []
        self.lock = asyncio.Lock()

    def _calculate_hash(self, prev_hash: str, timestamp: str, actor: str, action: str, target: str, payload_str: str) -> str:
        data = f"{prev_hash}|{timestamp}|{actor}|{action}|{target}|{payload_str}"
        return hashlib.sha256(data.encode('utf-8')).hexdigest()

    async def record_event(self, request: AuditRecordCreate) -> AuditRecord:
        async with self.lock:
            prev_hash = self.chain[-1].hash if self.chain else "GENESIS_HASH"
            timestamp = datetime.utcnow().isoformat()
            
            # Sort keys to guarantee deterministic JSON serialization
            payload_str = json.dumps(request.payload, sort_keys=True, separators=(',', ':'))
            
            new_hash = self._calculate_hash(
                prev_hash, timestamp, request.actor, request.action, request.target, payload_str
            )
            
            record = AuditRecord(
                id=f"evt_audit_{len(self.chain)+1}",
                timestamp=timestamp,
                actor=request.actor,
                action=request.action,
                target=request.target,
                payload=request.payload,
                prev_hash=prev_hash,
                hash=new_hash
            )
            self.chain.append(record)
            return record

    async def verify_chain(self) -> AuditVerificationResult:
        async with self.lock:
            if not self.chain:
                return AuditVerificationResult(is_valid=True, total_records=0)
            
            for i, record in enumerate(self.chain):
                expected_prev = "GENESIS_HASH" if i == 0 else self.chain[i-1].hash
                
                if record.prev_hash != expected_prev:
                    return AuditVerificationResult(
                        is_valid=False, 
                        total_records=len(self.chain),
                        broken_at_id=record.id, 
                        reason="Previous hash mismatch (Chain broken)"
                    )
                
                payload_str = json.dumps(record.payload, sort_keys=True, separators=(',', ':'))
                recalculated_hash = self._calculate_hash(
                    record.prev_hash, record.timestamp, record.actor, record.action, record.target, payload_str
                )
                
                if record.hash != recalculated_hash:
                    return AuditVerificationResult(
                        is_valid=False,
                        total_records=len(self.chain),
                        broken_at_id=record.id,
                        reason="Hash recalculation mismatch (Data tampered)"
                    )
                    
            return AuditVerificationResult(is_valid=True, total_records=len(self.chain))
