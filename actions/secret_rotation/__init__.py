"""secret_rotation — avtomatizirana rotacija skrivnosti (double-buffer, audit).

Javni API:
    SecretRotationManager(clock, value_generator)
        → register_secret / rotate / activate / due_secrets / status_of / revoke
"""

from actions.secret_rotation.rotation import (
    SecretRotationManager,
    SecretState,
    AuditEntry,
    default_value_generator,
)

__all__ = ["SecretRotationManager", "SecretState", "AuditEntry", "default_value_generator"]
