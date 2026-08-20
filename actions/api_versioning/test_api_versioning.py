"""
Tests for api_versioning module.
"""

import pytest
from fastapi.testclient import TestClient

from actions.api_versioning.main import app
from actions.api_versioning.api_versioning import VersionManager


# Create test client
client = TestClient(app)


class TestVersionManager:
    """Tests for VersionManager class."""
    
    def test_valid_semver(self):
        """Test valid semantic version formats."""
        assert VersionManager.is_valid_semver("1.0.0") is True
        assert VersionManager.is_valid_semver("2.1.3") is True
        assert VersionManager.is_valid_semver("0.0.1") is True
        assert VersionManager.is_valid_semver("10.20.30") is True
        assert VersionManager.is_valid_semver("1.0.0-alpha") is True
        assert VersionManager.is_valid_semver("1.0.0+build.123") is True
    
    def test_invalid_semver(self):
        """Test invalid semantic version formats."""
        assert VersionManager.is_valid_semver("") is False
        assert VersionManager.is_valid_semver("1.0") is False
        assert VersionManager.is_valid_semver("1") is False
        assert VersionManager.is_valid_semver("1.0.0.1") is False
        assert VersionManager.is_valid_semver("abc") is False
        assert VersionManager.is_valid_semver("1.0.0-") is False
        assert VersionManager.is_valid_semver(None) is False
        assert VersionManager.is_valid_semver(123) is False
    
    def test_version_manager_initialization(self):
        """Test VersionManager initialization."""
        vm = VersionManager("1.0.0", ["1.0.0", "1.1.0"])
        assert vm.current_version == "1.0.0"
        assert "1.0.0" in vm.supported_versions
        assert "1.1.0" in vm.supported_versions
    
    def test_invalid_initialization(self):
        """Test VersionManager with invalid versions."""
        with pytest.raises(ValueError):
            VersionManager("invalid", ["1.0.0"])
        
        with pytest.raises(ValueError):
            VersionManager("1.0.0", ["invalid"])
    
    def test_add_supported_version(self):
        """Test adding supported versions."""
        vm = VersionManager("1.0.0", ["1.0.0"])
        assert vm.add_supported_version("2.0.0") is True
        assert "2.0.0" in vm.supported_versions
        # Duplicate should return False
        assert vm.add_supported_version("2.0.0") is False
        # Invalid version should return False
        assert vm.add_supported_version("invalid") is False
    
    def test_deprecate_version(self):
        """Test deprecating versions."""
        vm = VersionManager("1.0.0", ["1.0.0", "1.1.0"])
        assert vm.deprecate_version("1.1.0") is True
        assert "1.1.0" in vm.deprecated_versions
        # Already deprecated should return False
        assert vm.deprecate_version("1.1.0") is False
        # Non-existent version should return False
        assert vm.deprecate_version("3.0.0") is False
    
    def test_validate_version_header(self):
        """Test version header validation."""
        vm = VersionManager("1.0.0", ["1.0.0", "1.1.0"])
        
        # Valid version
        is_valid, error = vm.validate_version_header("1.0.0")
        assert is_valid is True
        assert error == ""
        
        # Missing header
        is_valid, error = vm.validate_version_header(None)
        assert is_valid is False
        assert "Missing" in error
        
        # Invalid format
        is_valid, error = vm.validate_version_header("invalid")
        assert is_valid is False
        assert "Invalid" in error
        
        # Unsupported version
        is_valid, error = vm.validate_version_header("3.0.0")
        assert is_valid is False
        assert "not supported" in error


class TestAPIEndpoints:
    """Tests for FastAPI endpoints."""
    
    def test_health_endpoint_success(self):
        """Test health endpoint returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
        assert data["service"] == "enterprise-api-versioning"
    
    def test_protected_endpoint_with_valid_version(self):
        """Test protected endpoint with valid version header."""
        response = client.get(
            "/protected",
            headers={"Accept-Version": "1.0.0"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Access granted"
        assert data["api_version"] == "1.0.0"
    
    def test_protected_endpoint_with_another_valid_version(self):
        """Test protected endpoint with another valid version."""
        response = client.get(
            "/protected",
            headers={"Accept-Version": "2.0.0"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Access granted"
        assert data["api_version"] == "2.0.0"
    
    def test_protected_endpoint_missing_version(self):
        """Test protected endpoint without version header returns 406."""
        response = client.get("/protected")
        assert response.status_code == 406
        data = response.json()
        assert data["error"] == "Not Acceptable"
        assert "Missing" in data["message"]
    
    def test_protected_endpoint_invalid_version_format(self):
        """Test protected endpoint with invalid version format returns 406."""
        response = client.get(
            "/protected",
            headers={"Accept-Version": "invalid-version"}
        )
        assert response.status_code == 406
        data = response.json()
        assert data["error"] == "Not Acceptable"
        assert "Invalid" in data["message"]
    
    def test_protected_endpoint_unsupported_version(self):
        """Test protected endpoint with unsupported version returns 406."""
        response = client.get(
            "/protected",
            headers={"Accept-Version": "9.9.9"}
        )
        assert response.status_code == 406
        data = response.json()
        assert data["error"] == "Not Acceptable"
        assert "not supported" in data["message"]
    
    def test_version_info_endpoint(self):
        """Test version info endpoint."""
        response = client.get(
            "/version",
            headers={"Accept-Version": "1.0.0"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["current_version"] == "1.0.0"
        assert "1.0.0" in data["supported_versions"]
        assert "2.0.0" in data["supported_versions"]
    
    def test_health_endpoint_ignores_version(self):
        """Test health endpoint works without version header."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    
    def test_health_endpoint_with_invalid_version(self):
        """Test health endpoint works even with invalid version."""
        response = client.get(
            "/health",
            headers={"Accept-Version": "invalid"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"