"""api_version_manager — življenjski cikel API verzij (SemVer, deprecation, routing).

Javni API:
    VersionManager(rng) → register/list/route/deprecate/active_deprecations
    detect_breaking_change(old_schema, new_schema) → (is_breaking, changelog)
    SemVer.parse("1.2.3") → SemVer
"""

from actions.api_version_manager.version_manager import (
    SemVer,
    VersionManager,
    VersionRoute,
)

__all__ = ["SemVer", "VersionManager", "VersionRoute"]
