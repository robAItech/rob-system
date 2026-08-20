from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from actions.auth_vault.schemas import ApiKeyCreate, ApiKeyResponse, TokenVerifyRequest, VaultEncryptRequest, VaultDecryptRequest
from actions.auth_vault.auth_vault import AuthVault

app = FastAPI(title="Rob AI Studio - Enterprise Auth Vault API")
vault = AuthVault()

@app.post("/keys/issue", response_model=ApiKeyResponse)
async def issue_key(request: ApiKeyCreate):
    return vault.generate_api_key(request)

@app.post("/keys/verify")
async def verify_key(request: TokenVerifyRequest):
    valid, code, msg = vault.verify_api_key(request.api_key, request.required_role)
    if not valid:
        status_code = status.HTTP_401_UNAUTHORIZED if code != "FORBIDDEN" else status.HTTP_403_FORBIDDEN
        return JSONResponse(status_code=status_code, content={"error": code, "detail": msg})
    return {"status": "AUTHORIZED", "detail": msg}

@app.post("/vault/encrypt")
async def encrypt_payload(request: VaultEncryptRequest):
    cipher = vault.encrypt_data(request.plain_text)
    return {"cipher_text": cipher}

@app.post("/vault/decrypt")
async def decrypt_payload(request: VaultDecryptRequest):
    plain = vault.decrypt_data(request.cipher_text)
    if plain is None:
        raise HTTPException(status_code=400, detail="Invalid cipher text or tampered payload")
    return {"plain_text": plain}
