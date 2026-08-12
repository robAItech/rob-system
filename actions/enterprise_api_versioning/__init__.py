"""
Enterprise API Versioning Module
Handles API version validation and management for enterprise applications.
"""

from actions.enterprise_api_versioning.enterprise_api_versioning import VersionManager
from actions.enterprise_api_versioning.main import app

__all__ = ["VersionManager", "app"]
__version__ = "1.0.0"