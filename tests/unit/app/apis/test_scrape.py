"""Tests for the scraping functionality."""

import asyncio
from datetime import datetime
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status

from app.apis.scrape import ScrapeRequest, queue_scraping


def test_scrape_request_validation():
    """Test ScrapeRequest validation."""
    # Test valid request
    request = ScrapeRequest(
        url="https://suumo.jp/ms/chintai/tokyo/sc_shinjuku/",
        line_user_id="U1234567890abcdef1234567890abcdef",
        timestamp=datetime.now(),
    )
    assert request.url == "https://suumo.jp/ms/chintai/tokyo/sc_shinjuku/"
    assert request.line_user_id == "U1234567890abcdef1234567890abcdef"
    assert request.check_only is False

    # Test invalid URL
    with pytest.raises(ValueError, match="url must start with https://suumo.jp/ms"):
        ScrapeRequest(
            url="https://invalid.com",
            line_user_id="U1234567890abcdef1234567890abcdef",
            timestamp=datetime.now(),
        )

    # Test invalid line_user_id
    with pytest.raises(ValueError, match="line_user_id must start with U"):
        ScrapeRequest(
            url="https://suumo.jp/ms/chintai/tokyo/sc_shinjuku/",
            line_user_id="invalid",
            timestamp=datetime.now(),
        )


class TestQueueScraping:
    """Tests for the queue_scraping function."""

    @pytest.fixture
    def mock_publisher(self) -> Generator[MagicMock, None, None]:
        """Mock the Pub/Sub publisher."""
        mock_publisher = MagicMock()
        with patch("app.apis.scrape.get_publisher", return_value=mock_publisher) as _:
            yield mock_publisher

    @pytest.mark.asyncio
    async def test_queue_scraping_success(self, mock_publisher: MagicMock) -> None:
        """Test successful scraping request."""
        # Arrange
        url = "https://suumo.jp/ms/chintai/tokyo/sc_shinjuku/"
        line_user_id = "U1234567890abcdef1234567890abcdef"
        request = ScrapeRequest(
            url=url, line_user_id=line_user_id, timestamp=datetime.now()
        )

        # Configure the mock
        mock_future = MagicMock()
        mock_future.result.return_value = "test_message_id"
        mock_publisher.publish.return_value = mock_future

        # Act
        result = await queue_scraping(request)

        # Assert
        assert result["status"] == "queued"
        assert result["message"] == "Scraping request has been queued"
        assert result["message_id"] == "test_message_id"
        mock_publisher.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_queue_scraping_with_check_only(
        self, mock_publisher: MagicMock
    ) -> None:
        """Test scraping request with check_only flag."""
        # Arrange
        url = "https://suumo.jp/ms/chintai/tokyo/sc_shinjuku/"
        line_user_id = "U1234567890abcdef1234567890abcdef"
        request = ScrapeRequest(
            url=url,
            line_user_id=line_user_id,
            check_only=True,
            timestamp=datetime.now(),
        )

        # Configure the mock
        mock_future = MagicMock()
        mock_future.result.return_value = "test_message_id"
        mock_publisher.publish.return_value = mock_future

        # Act
        result = await queue_scraping(request)

        # Assert
        assert result["status"] == "queued"
        assert result["message"] == "Scraping request has been queued"
        assert result["message_id"] == "test_message_id"
        mock_publisher.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_queue_scraping_timeout(self, mock_publisher: MagicMock) -> None:
        """Test timeout while publishing message."""
        # Arrange
        url = "https://suumo.jp/ms/chintai/tokyo/sc_shinjuku/"
        line_user_id = "U1234567890abcdef1234567890abcdef"
        request = ScrapeRequest(
            url=url, line_user_id=line_user_id, timestamp=datetime.now()
        )

        # Configure the mock to raise TimeoutError
        mock_future = MagicMock()
        mock_future.result.side_effect = asyncio.TimeoutError()
        mock_publisher.publish.return_value = mock_future

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await queue_scraping(request)

        assert exc_info.value.status_code == status.HTTP_504_GATEWAY_TIMEOUT
        assert "Timeout while publishing message" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_queue_scraping_error(self, mock_publisher: MagicMock) -> None:
        """Test error while publishing message."""
        # Arrange
        url = "https://suumo.jp/ms/chintai/tokyo/sc_shinjuku/"
        line_user_id = "U1234567890abcdef1234567890abcdef"
        request = ScrapeRequest(
            url=url, line_user_id=line_user_id, timestamp=datetime.now()
        )

        # Configure the mock to raise an error
        mock_publisher.publish.side_effect = Exception("Test error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await queue_scraping(request)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Error queuing scraping request" in exc_info.value.detail
