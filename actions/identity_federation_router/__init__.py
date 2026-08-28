"""identity_federation_router — OAuth2/OIDC federacija (enterprise).

Javni API:
    IdentityFederationRouter()
        → register_idp / authorization_code_url / exchange_code
        → client_credentials_flow / device_flow_start/approve/poll / validate
    create_jwt / validate_jwt / parse_jwt  (HS256, stdlib)
"""

from actions.identity_federation_router.federation import (
    IdPConfig,
    TokenContext,
    IdentityFederationRouter,
    FederationError,
    create_jwt,
    parse_jwt,
    validate_jwt,
)

__all__ = [
    "IdPConfig",
    "TokenContext",
    "IdentityFederationRouter",
    "FederationError",
    "create_jwt",
    "parse_jwt",
    "validate_jwt",
]
