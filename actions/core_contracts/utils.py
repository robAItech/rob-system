"""
Core utility classes for enterprise applications.

This module contains stateless utility classes:
- TimestampNormalizer: Normalizes timestamps to ISO 8601 UTC format
- HashUtils: Provides SHA256 hashing utilities
"""

import hashlib
import re
from datetime import datetime, timezone, timedelta
from typing import Union, Optional


class TimestampNormalizer:
    """
    Utility class for normalizing timestamps to ISO 8601 UTC format.

    This class provides static methods to normalize various timestamp formats
    to a consistent ISO 8601 UTC representation with '+00:00' offset.
    """

    # Regex pattern for ISO 8601 timestamps with optional timezone
    _ISO_PATTERN = re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
        r"(\.\d{1,6})?"
        r"(Z|[+-]\d{2}:\d{2})?$"
    )

    @staticmethod
    def normalize(value: Union[datetime, str]) -> str:
        """
        Normalize a datetime object or ISO string to ISO 8601 UTC format.

        Args:
            value: A datetime object or ISO 8601 string

        Returns:
            Normalized ISO 8601 string in UTC with '+00:00' offset

        Raises:
            TypeError: If value is not a datetime or string
            ValueError: If string is not a valid ISO 8601 timestamp
        """
        if isinstance(value, datetime):
            return TimestampNormalizer._normalize_datetime(value)
        elif isinstance(value, str):
            return TimestampNormalizer._normalize_string(value)
        else:
            raise TypeError(
                f"Expected datetime or str, got {type(value).__name__}"
            )

    @staticmethod
    def validate(value: str) -> bool:
        """
        Validate if a string is a valid ISO 8601 timestamp.

        Args:
            value: String to validate

        Returns:
            True if valid ISO 8601 timestamp, False otherwise
        """
        if not isinstance(value, str) or not value:
            return False

        if not TimestampNormalizer._ISO_PATTERN.match(value):
            return False

        try:
            TimestampNormalizer._parse_iso_string(value)
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _normalize_datetime(dt: datetime) -> str:
        """
        Normalize a datetime object to ISO 8601 UTC format.

        Args:
            dt: Datetime object to normalize

        Returns:
            Normalized ISO 8601 string in UTC
        """
        # If naive, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            # Convert to UTC
            dt = dt.astimezone(timezone.utc)

        # Format with microseconds if present
        if dt.microsecond:
            return dt.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
        else:
            return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    @staticmethod
    def _normalize_string(value: str) -> str:
        """
        Normalize an ISO 8601 string to UTC format.

        Args:
            value: ISO 8601 string to normalize

        Returns:
            Normalized ISO 8601 string in UTC

        Raises:
            ValueError: If string is not a valid ISO 8601 timestamp
        """
        dt = TimestampNormalizer._parse_iso_string(value)
        return TimestampNormalizer._normalize_datetime(dt)

    @staticmethod
    def _parse_iso_string(value: str) -> datetime:
        """
        Parse an ISO 8601 string into a datetime object.

        Args:
            value: ISO 8601 string to parse

        Returns:
            Parsed datetime object

        Raises:
            ValueError: If string is not a valid ISO 8601 timestamp
        """
        if not value:
            raise ValueError("Empty string is not a valid timestamp")

        # Handle Z suffix
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        try:
            return datetime.fromisoformat(value)
        except ValueError as e:
            raise ValueError(f"Invalid ISO 8601 timestamp: {value}") from e


class HashUtils:
    """
    Utility class for SHA256 hashing operations.

    This class provides static methods for hashing strings and verifying
    hashes using the SHA256 algorithm.
    """

    # SHA256 hash pattern (64 hex characters)
    _HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")

    @staticmethod
    def sha256(data: str, encoding: str = "utf-8") -> str:
        """
        Compute SHA256 hash of a string.

        Args:
            data: String to hash
            encoding: Character encoding to use (default: utf-8)

        Returns:
            Hexadecimal SHA256 hash string

        Raises:
            TypeError: If data is not a string
            ValueError: If encoding is invalid
        """
        if not isinstance(data, str):
            raise TypeError(f"Expected str, got {type(data).__name__}")

        try:
            encoded_data = data.encode(encoding)
        except (LookupError, UnicodeEncodeError) as e:
            raise ValueError(f"Invalid encoding '{encoding}': {e}") from e

        return hashlib.sha256(encoded_data).hexdigest()

    @staticmethod
    def verify(data: str, expected_hash: str, encoding: str = "utf-8") -> bool:
        """
        Verify if a string matches a given SHA256 hash.

        Args:
            data: String to verify
            expected_hash: Expected SHA256 hash (hex string)
            encoding: Character encoding to use (default: utf-8)

        Returns:
            True if hash matches, False otherwise

        Raises:
            TypeError: If data or expected_hash is not a string
            ValueError: If encoding is invalid
        """
        if not isinstance(data, str):
            raise TypeError(f"Expected str for data, got {type(data).__name__}")

        if not isinstance(expected_hash, str):
            raise TypeError(
                f"Expected str for expected_hash, got {type(expected_hash).__name__}"
            )

        computed_hash = HashUtils.sha256(data, encoding)
        return computed_hash.lower() == expected_hash.lower()

    @staticmethod
    def is_valid_hash(hash_str: str) -> bool:
        """
        Check if a string is a valid SHA256 hash.

        Args:
            hash_str: String to check

        Returns:
            True if valid SHA256 hash, False otherwise
        """
        if not isinstance(hash_str, str) or not hash_str:
            return False

        return bool(HashUtils._HASH_PATTERN.match(hash_str.lower()))