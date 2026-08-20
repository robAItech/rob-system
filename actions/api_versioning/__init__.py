"""
Enterprise API Versioning Module
Handles API version validation and management for enterprise applications.
"""

from actions.api_versioning.api_versioning import VersionManager
from actions.api_versioning.main import app

__all__ = ["VersionManager", "app"]
__version__ = "1.0.0"