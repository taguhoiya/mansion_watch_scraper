"""Tests for the scraping functionality."""

import asyncio
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status

from app.apis.scrape import ScrapeRequest, queue_scraping


class TestQueueScraping:
    """Tests for the queue_scraping function."""

    @pytest.fixture
    def mock_publisher(self) -> Generator[MagicMock, None, None]:
        """Mock the Pub/Sub publisher."""
        with patch("app.apis.scrape.publisher") as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_queue_scraping_success(self, mock_publisher: MagicMock) -> None:
        """Test successful scraping request."""
        # Arrange
        url = "https://suumo.jp/ms/chintai/tokyo/sc_shinjuku/"
        line_user_id = "U1234567890abcdef1234567890abcdef"
        request = ScrapeRequest(url=url, line_user_id=line_user_id)

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
        request = ScrapeRequest(url=url, line_user_id=line_user_id)

        # Configure the mock to raise TimeoutError
        mock_future = MagicMock()
        mock_future.result.side_effect = asyncio.TimeoutError()
        mock_publisher.publish.return_value = mock_future

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await queue_scraping(request)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Error queuing scraping request" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_queue_scraping_error(self, mock_publisher: MagicMock) -> None:
        """Test error while publishing message."""
        # Arrange
        url = "https://suumo.jp/ms/chintai/tokyo/sc_shinjuku/"
        line_user_id = "U1234567890abcdef1234567890abcdef"
        request = ScrapeRequest(url=url, line_user_id=line_user_id)

        # Configure the mock to raise an error
        mock_publisher.publish.side_effect = Exception("Test error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await queue_scraping(request)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Error queuing scraping request" in exc_info.value.detail
