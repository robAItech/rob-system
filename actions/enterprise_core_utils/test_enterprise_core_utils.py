"""
Pytest tests for the enterprise_core_utils module.

These tests provide 100% coverage of the utility classes and API endpoints.
"""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from actions.enterprise_core_utils.enterprise_core_utils import (
    TimestampNormalizer,
    HashUtils,
)
from actions.enterprise_core_utils.main import app


class TestTimestampNormalizer:
    """Test cases for TimestampNormalizer class."""

    def test_normalize_datetime_utc(self):
        """Test normalizing a UTC datetime object."""
        dt = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        result = TimestampNormalizer.normalize(dt)
        assert result == "2024-01-15T10:30:45+00:00"

    def test_normalize_datetime_with_offset(self):
        """Test normalizing a datetime with timezone offset."""
        dt = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone(timedelta(hours=2)))
        result = TimestampNormalizer.normalize(dt)
        assert result == "2024-01-15T08:30:45+00:00"

    def test_normalize_naive_datetime(self):
        """Test normalizing a naive datetime (assumed UTC)."""
        dt = datetime(2024, 1, 15, 10, 30, 45)
        result = TimestampNormalizer.normalize(dt)
        assert result == "2024-01-15T10:30:45+00:00"

    def test_normalize_iso_string_z(self):
        """Test normalizing ISO string with Z suffix."""
        result = TimestampNormalizer.normalize("2024-01-15T10:30:45Z")
        assert result == "2024-01-15T10:30:45+00:00"

    def test_normalize_iso_string_offset(self):
        """Test normalizing ISO string with offset."""
        result = TimestampNormalizer.normalize("2024-01-15T10:30:45+02:00")
        assert result == "2024-01-15T08:30:45+00:00"

    def test_normalize_iso_string_microseconds(self):
        """Test normalizing ISO string with microseconds."""
        result = TimestampNormalizer.normalize("2024-01-15T10:30:45.123456Z")
        assert result == "2024-01-15T10:30:45.123456+00:00"

    def test_normalize_invalid_type(self):
        """Test normalizing with invalid type raises TypeError."""
        with pytest.raises(TypeError):
            TimestampNormalizer.normalize(12345)

    def test_normalize_invalid_string(self):
        """Test normalizing invalid string raises ValueError."""
        with pytest.raises(ValueError):
            TimestampNormalizer.normalize("not-a-timestamp")

    def test_validate_valid_z(self):
        """Test validating valid ISO string with Z suffix."""
        assert TimestampNormalizer.validate("2024-01-15T10:30:45Z") is True

    def test_validate_valid_offset(self):
        """Test validating valid ISO string with offset."""
        assert TimestampNormalizer.validate("2024-01-15T10:30:45+02:00") is True

    def test_validate_valid_microseconds(self):
        """Test validating valid ISO string with microseconds."""
        assert TimestampNormalizer.validate("2024-01-15T10:30:45.123456Z") is True

    def test_validate_invalid_format(self):
        """Test validating invalid format returns False."""
        assert TimestampNormalizer.validate("2024-13-45T10:30:45Z") is False

    def test_validate_invalid_date(self):
        """Test validating invalid date returns False."""
        assert TimestampNormalizer.validate("2024-13-45T10:30:45Z") is False

    def test_validate_non_string(self):
        """Test validating non-string returns False."""
        assert TimestampNormalizer.validate(12345) is False

    def test_validate_empty_string(self):
        """Test validating empty string returns False."""
        assert TimestampNormalizer.validate("") is False

    def test_validate_missing_time(self):
        """Test validating string without time component returns False."""
        assert TimestampNormalizer.validate("2024-01-15") is False


class TestHashUtils:
    """Test cases for HashUtils class."""

    def test_sha256_basic(self):
        """Test basic SHA256 hashing."""
        result = HashUtils.sha256("hello")
        assert result == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"

    def test_sha256_empty_string(self):
        """Test SHA256 of empty string."""
        result = HashUtils.sha256("")
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_sha256_unicode(self):
        """Test SHA256 with unicode characters."""
        result = HashUtils.sha256("héllo wörld")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_sha256_special_characters(self):
        """Test SHA256 with special characters."""
        result = HashUtils.sha256("!@#$%^&*()_+-=[]{}|;':\",./<>?")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_sha256_long_string(self):
        """Test SHA256 with a long string."""
        long_string = "a" * 10000
        result = HashUtils.sha256(long_string)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_sha256_invalid_type(self):
        """Test SHA256 with invalid type raises TypeError."""
        with pytest.raises(TypeError):
            HashUtils.sha256(12345)

    def test_sha256_invalid_encoding(self):
        """Test SHA256 with invalid encoding raises ValueError."""
        with pytest.raises(ValueError):
            HashUtils.sha256("hello", encoding="invalid-encoding")

    def test_verify_correct_hash(self):
        """Test verifying correct hash returns True."""
        data = "hello"
        hash_value = HashUtils.sha256(data)
        assert HashUtils.verify(data, hash_value) is True

    def test_verify_incorrect_hash(self):
        """Test verifying incorrect hash returns False."""
        data = "hello"
        wrong_hash = "0" * 64
        assert HashUtils.verify(data, wrong_hash) is False

    def test_verify_uppercase_hash(self):
        """Test verifying with uppercase hash returns True."""
        data = "hello"
        hash_value = HashUtils.sha256(data).upper()
        assert HashUtils.verify(data, hash_value) is True

    def test_verify_invalid_hash_type(self):
        """Test verifying with invalid hash type raises TypeError."""
        with pytest.raises(TypeError):
            HashUtils.verify("hello", 12345)

    def test_verify_invalid_data_type(self):
        """Test verifying with invalid data type raises TypeError."""
        with pytest.raises(TypeError):
            HashUtils.verify(12345, "0" * 64)

    def test_is_valid_hash_valid(self):
        """Test validating a valid hash."""
        valid_hash = "a" * 64
        assert HashUtils.is_valid_hash(valid_hash) is True

    def test_is_valid_hash_uppercase(self):
        """Test validating an uppercase hash."""
        valid_hash = "A" * 64
        assert HashUtils.is_valid_hash(valid_hash) is True

    def test_is_valid_hash_too_short(self):
        """Test validating a hash that is too short."""
        short_hash = "a" * 63
        assert HashUtils.is_valid_hash(short_hash) is False

    def test_is_valid_hash_too_long(self):
        """Test validating a hash that is too long."""
        long_hash = "a" * 65
        assert HashUtils.is_valid_hash(long_hash) is False

    def test_is_valid_hash_invalid_chars(self):
        """Test validating a hash with invalid characters."""
        invalid_hash = "g" * 64
        assert HashUtils.is_valid_hash(invalid_hash) is False

    def test_is_valid_hash_non_string(self):
        """Test validating a non-string value."""
        assert HashUtils.is_valid_hash(12345) is False

    def test_is_valid_hash_empty(self):
        """Test validating an empty string."""
        assert HashUtils.is_valid_hash("") is False


class TestAPI:
    """Test cases for FastAPI endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client for the FastAPI app."""
        return TestClient(app)

    def test_health_endpoint(self, client):
        """Test the health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"
        assert "timestamp" in data

    def test_root_endpoint(self, client):
        """Test the root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "enterprise_core_utils"
        assert data["version"] == "1.0.0"
        assert "message" in data

    def test_health_timestamp_valid(self, client):
        """Test that health endpoint returns a valid timestamp."""
        response = client.get("/health")
        data = response.json()
        assert TimestampNormalizer.validate(data["timestamp"]) is True