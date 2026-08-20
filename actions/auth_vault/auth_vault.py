import hmac
import hashlib
import secrets
import base64
from typing import Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from actions.auth_vault.schemas import Role, ApiKeyCreate, ApiKeyResponse

class EnterpriseAuthVault:
    def __init__(self, secret_seed: str = "rob_ai_studio_master_vault_key_2026"):
        self.secret_seed = secret_seed.encode("utf-8")
        self.active_keys: Dict[str, Dict[str, Any]] = {}

    def _hash_key(self, api_key: str) -> str:
        return hmac.new(self.secret_seed, api_key.encode("utf-8"), hashlib.sha256).hexdigest()

    def generate_api_key(self, request: ApiKeyCreate) -> ApiKeyResponse:
        raw_key = f"rob_{secrets.token_urlsafe(32)}"
        hashed = self._hash_key(raw_key)
        
        expires_at = datetime.utcnow() + timedelta(days=request.ttl_days)
        
        self.active_keys[hashed] = {
            "client_id": request.client_id,
            "role": request.role,
            "expires_at": expires_at,
            "created_at": datetime.utcnow()
        }

        return ApiKeyResponse(
            client_id=request.client_id,
            api_key=raw_key,
            role=request.role,
            created_at=datetime.utcnow()
        )

    def verify_api_key(self, api_key: str, required_role: Role = Role.READ_ONLY) -> Tuple[bool, str, str]:
        hashed = self._hash_key(api_key)
        record = self.active_keys.get(hashed)

        if not record:
            return False, "INVALID_KEY", "API key does not exist or has been revoked."

        if datetime.utcnow() > record["expires_at"]:
            return False, "KEY_EXPIRED", "API key has expired."

        role_hierarchy = {Role.READ_ONLY: 1, Role.DEVELOPER: 2, Role.ADMIN: 3}
        user_role_level = role_hierarchy.get(record["role"], 0)
        required_role_level = role_hierarchy.get(required_role, 0)

        if user_role_level < required_role_level:
            return False, "FORBIDDEN", f"Role '{record['role'].value}' insufficient for required '{required_role.value}'."

        return True, "AUTHORIZED", f"Authenticated as {record['client_id']}"

    def encrypt_data(self, plain_text: str) -> str:
        encoded = base64.b64encode(plain_text.encode("utf-8")).decode("utf-8")
        signature = hmac.new(self.secret_seed, encoded.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
        return f"enc_v1:{signature}:{encoded}"

    def decrypt_data(self, cipher_text: str) -> Optional[str]:
        parts = cipher_text.split(":")
        if len(parts) != 3 or parts[0] != "enc_v1":
            return None
        
        signature, encoded = parts[1], parts[2]
        expected_sig = hmac.new(self.secret_seed, encoded.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
        
        if not hmac.compare_digest(signature, expected_sig):
            return None
            
        return base64.b64decode(encoded.encode("utf-8")).decode("utf-8")
