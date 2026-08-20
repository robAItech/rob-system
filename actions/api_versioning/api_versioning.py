"""
Core version management logic for api_versioning module.
"""

import re
from typing import Optional, List, Dict, Any
from datetime import datetime


class VersionManager:
    """
    Manages API versioning with validation and compatibility checks.
    """
    
    def __init__(self, current_version: str = "1.0.0", supported_versions: Optional[List[str]] = None):
        """
        Initialize the VersionManager.
        
        Args:
            current_version: The current API version
            supported_versions: List of supported versions
        """
        self.current_version = current_version
        self.supported_versions = supported_versions or [current_version]
        self.deprecated_versions: List[str] = []
        self.version_history: List[Dict[str, Any]] = []
        
        # Validate initial versions
        if not self.is_valid_semver(current_version):
            raise ValueError(f"Invalid current version format: {current_version}")
        
        for version in self.supported_versions:
            if not self.is_valid_semver(version):
                raise ValueError(f"Invalid supported version format: {version}")
    
    @staticmethod
    def is_valid_semver(version: str) -> bool:
        """
        Validate if a version string follows Semantic Versioning (SemVer) format.
        
        Args:
            version: Version string to validate
            
        Returns:
            bool: True if valid SemVer, False otherwise
        """
        if not isinstance(version, str) or not version:
            return False
        
        # SemVer pattern: MAJOR.MINOR.PATCH[-prerelease][+build]
        pattern = r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'
        
        return bool(re.match(pattern, version))
    
    def is_supported(self, version: str) -> bool:
        """
        Check if a version is supported.
        
        Args:
            version: Version to check
            
        Returns:
            bool: True if version is supported
        """
        return version in self.supported_versions
    
    def is_deprecated(self, version: str) -> bool:
        """
        Check if a version is deprecated.
        
        Args:
            version: Version to check
            
        Returns:
            bool: True if version is deprecated
        """
        return version in self.deprecated_versions
    
    def add_supported_version(self, version: str) -> bool:
        """
        Add a new supported version.
        
        Args:
            version: Version to add
            
        Returns:
            bool: True if added successfully
        """
        if not self.is_valid_semver(version):
            return False
        
        if version not in self.supported_versions:
            self.supported_versions.append(version)
            self.supported_versions.sort(key=lambda v: [int(x) for x in v.split('.')[:3]])
            return True
        return False
    
    def deprecate_version(self, version: str) -> bool:
        """
        Deprecate a version.
        
        Args:
            version: Version to deprecate
            
        Returns:
            bool: True if deprecated successfully
        """
        if version in self.supported_versions and version not in self.deprecated_versions:
            self.deprecated_versions.append(version)
            return True
        return False
    
    def get_version_info(self) -> Dict[str, Any]:
        """
        Get version information.
        
        Returns:
            Dict with version information
        """
        return {
            "current_version": self.current_version,
            "supported_versions": self.supported_versions,
            "deprecated_versions": self.deprecated_versions,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def validate_version_header(self, version_header: Optional[str]) -> tuple[bool, str]:
        """
        Validate the Accept-Version header.
        
        Args:
            version_header: The Accept-Version header value
            
        Returns:
            tuple: (is_valid, error_message)
        """
        if not version_header:
            return False, "Missing Accept-Version header"
        
        if not self.is_valid_semver(version_header):
            return False, f"Invalid version format: {version_header}"
        
        if not self.is_supported(version_header):
            return False, f"Version {version_header} is not supported"
        
        return True, ""