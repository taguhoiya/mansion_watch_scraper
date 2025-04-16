"""Tests for the dates module."""

import datetime
from unittest.mock import patch

from app.services.dates import get_current_time


def test_get_current_time():
    """Test get_current_time returns a datetime."""
    result = get_current_time()
    assert isinstance(result, datetime.datetime)
    assert result.tzinfo is not None  # Should be timezone-aware


def test_get_current_time_mocked():
    """Test get_current_time with a mocked datetime."""
    mock_now = datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    expected_result = mock_now + datetime.timedelta(hours=9)

    with patch("app.services.dates.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        mock_datetime.timezone.utc = datetime.timezone.utc
        mock_datetime.timedelta = datetime.timedelta

        result = get_current_time()

        assert result == expected_result
        mock_datetime.now.assert_called_once_with(datetime.timezone.utc)
