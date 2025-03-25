"""Extended tests for the webhooks API."""

import json
from datetime import datetime
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from linebot.v3.webhooks import MessageEvent, Source, TextMessageContent
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.apis.webhooks import (
    PropertyStatus,
    extract_urls,
    handle_follow_event,
    handle_http_exception,
    handle_scraping,
    is_valid_property_url,
    process_follow_event,
    process_text_message,
    send_push_message,
    webhook_message_handler,
)
from app.models.apis.webhook import WebhookResponse


@pytest.fixture(autouse=True)
async def mock_mongodb():
    """Mock MongoDB initialization for all tests."""
    mock_client = MagicMock(spec=AsyncIOMotorClient)
    mock_db = MagicMock(spec=AsyncIOMotorDatabase)
    mock_collection = AsyncMock()
    mock_db.__getitem__.return_value = mock_collection
    mock_client.__getitem__.return_value = mock_db

    with (
        patch("app.db.session._client", mock_client),
        patch("app.db.session.get_client", return_value=mock_client),
        patch("app.db.session.init_db", return_value=None),
        patch(
            "app.apis.webhooks.get_database_collections",
            return_value={"users": mock_collection},
        ),
    ):
        yield mock_client


@pytest.mark.webhook
class TestHandleScrapingFunction:
    """Tests for the handle_scraping function."""

    @pytest.fixture
    def mock_send_reply(self) -> Generator[AsyncMock, None, None]:
        """Mock the send_reply function."""
        with patch("app.apis.webhooks.send_reply", autospec=True) as mock:
            mock.return_value = None
            yield mock

    @pytest.fixture
    def mock_queue_scraping(self) -> Generator[AsyncMock, None, None]:
        """Mock the queue_scraping function."""
        with patch("app.apis.webhooks.queue_scraping", autospec=True) as mock:
            mock.return_value = {
                "status": "queued",
                "message": "Scraping request has been queued",
            }
            yield mock

    @pytest.fixture
    def mock_get_property_status(self) -> Generator[AsyncMock, None, None]:
        """Mock the get_property_status function."""
        with patch("app.apis.webhooks.get_property_status", autospec=True) as mock:
            mock.return_value = PropertyStatus(exists=False, user_has_access=False)
            yield mock

    @pytest.mark.asyncio
    async def test_handle_scraping_success(
        self,
        mock_send_reply: AsyncMock,
        mock_queue_scraping: AsyncMock,
        mock_get_property_status: AsyncMock,
    ) -> None:
        """Test successful scraping process."""
        # Arrange
        reply_token = "test_reply_token"
        url = "https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/"
        line_user_id = "U1234567890abcdef1234567890abcdef"

        # We need to mock send_push_message
        with patch(
            "app.apis.webhooks.send_push_message", autospec=True
        ) as mock_send_push:
            mock_send_push.return_value = None

            # Act
            await handle_scraping(reply_token, url, line_user_id)

            # Assert
            # Only one send_reply call for the success message
            assert mock_send_reply.call_count == 1
            mock_send_reply.assert_called_once_with(
                reply_token,
                "ウォッチリストに追加されました！\n左下のメニューからご確認ください😊\n(反映には1分ほどかかる場合があります)",
            )

            # No push message should be sent for success case
            mock_send_push.assert_not_called()

            # Verify queue_scraping was called with correct parameters
            mock_queue_scraping.assert_called_once()
            scrape_request = mock_queue_scraping.call_args[0][0]
            assert scrape_request.url == url
            assert scrape_request.line_user_id == line_user_id

    @pytest.mark.asyncio
    async def test_handle_scraping_property_not_found(
        self,
        mock_send_reply: AsyncMock,
        mock_queue_scraping: AsyncMock,
        mock_get_property_status: AsyncMock,
    ) -> None:
        """Test handling a property not found (404) response from the scrape endpoint."""
        # Arrange
        reply_token = "test_reply_token"
        url = "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_98246732/"
        line_user_id = "U1234567890abcdef1234567890abcdef"

        # Mock the response from queue_scraping with a not_found status
        mock_queue_scraping.return_value = None
        mock_queue_scraping.side_effect = HTTPException(
            status_code=404,
            detail="Property not found (404). The URL may be incorrect or the property listing may have been removed.",
        )

        # We need to mock send_push_message
        with patch(
            "app.apis.webhooks.send_push_message", autospec=True
        ) as mock_send_push:
            mock_send_push.return_value = None

            # Act
            await handle_scraping(reply_token, url, line_user_id)

            # Assert
            # Only one send_reply call for the success message
            assert mock_send_reply.call_count == 1
            mock_send_reply.assert_called_once_with(
                reply_token,
                "ウォッチリストに追加されました！\n左下のメニューからご確認ください😊\n(反映には1分ほどかかる場合があります)",
            )

            # Property not found message sent as push message
            mock_send_push.assert_called_once_with(
                line_user_id,
                "指定された物件は見つかりませんでした。URLが正しいか、または物件が削除されていないか確認してください。",
            )

            # Verify queue_scraping was called with correct parameters
            mock_queue_scraping.assert_called_once()
            scrape_request = mock_queue_scraping.call_args[0][0]
            assert scrape_request.url == url
            assert scrape_request.line_user_id == line_user_id

    @pytest.mark.asyncio
    async def test_handle_scraping_http_exception(
        self,
        mock_send_reply: AsyncMock,
        mock_queue_scraping: AsyncMock,
        mock_get_property_status: AsyncMock,
    ) -> None:
        """Test handling of HTTPException during scraping."""
        # Arrange
        reply_token = "test_reply_token"
        url = "https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/"
        line_user_id = "U1234567890abcdef1234567890abcdef"
        mock_queue_scraping.side_effect = HTTPException(
            status_code=500, detail="Internal server error"
        )

        # We need to mock send_push_message
        with patch(
            "app.apis.webhooks.send_push_message", autospec=True
        ) as mock_send_push:
            mock_send_push.return_value = None

            # Act
            await handle_scraping(reply_token, url, line_user_id)

            # Assert
            # Only one send_reply call for the success message
            assert mock_send_reply.call_count == 1
            mock_send_reply.assert_called_once_with(
                reply_token,
                "ウォッチリストに追加されました！\n左下のメニューからご確認ください😊\n(反映には1分ほどかかる場合があります)",
            )

            # Error message sent as push message
            mock_send_push.assert_called_once_with(
                line_user_id,
                "申し訳ありません。リクエストの処理中にエラーが発生しました。後でもう一度お試しください。",
            )

    @pytest.mark.asyncio
    async def test_handle_scraping_general_exception(
        self,
        mock_send_reply: AsyncMock,
        mock_queue_scraping: AsyncMock,
        mock_get_property_status: AsyncMock,
    ) -> None:
        """Test handling of general exceptions during scraping."""
        # Arrange
        reply_token = "test_reply_token"
        url = "https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/"
        line_user_id = "U1234567890abcdef1234567890abcdef"

        # Configure the mock to raise an exception on the second call
        mock_send_reply.side_effect = [None, Exception("Test exception")]

        # We need to mock send_push_message
        with patch(
            "app.apis.webhooks.send_push_message", autospec=True
        ) as mock_send_push:
            mock_send_push.return_value = None

            # Also mock the general exception in queue_scraping
            mock_queue_scraping.side_effect = Exception("General error")

            # Act
            await handle_scraping(reply_token, url, line_user_id)

            # Assert
            mock_send_reply.assert_called_once_with(
                reply_token,
                "ウォッチリストに追加されました！\n左下のメニューからご確認ください😊\n(反映には1分ほどかかる場合があります)",
            )

            # Error message sent as push message
            mock_send_push.assert_called_once_with(
                line_user_id,
                "申し訳ありません。リクエストの処理中にエラーが発生しました。後でもう一度お試しください。",
            )


@pytest.mark.webhook
class TestHandleScrapingError:
    """Tests for the handle_scraping_error function."""

    @pytest.fixture
    def mock_send_push_message(self) -> Generator[AsyncMock, None, None]:
        """Mock the send_push_message function."""
        with patch("app.apis.webhooks.send_push_message", autospec=True) as mock:
            mock.return_value = None
            yield mock

    @pytest.mark.asyncio
    async def test_handle_scraping_error_connection_error(
        self, mock_send_push_message: AsyncMock
    ) -> None:
        """Test handling a connection error."""
        # Arrange
        line_user_id = "U1234567890abcdef1234567890abcdef"
        error = HTTPException(
            status_code=500, detail="ConnectionError: Failed to establish a connection"
        )

        # Act
        await handle_http_exception(error, line_user_id)

        # Assert
        mock_send_push_message.assert_called_once_with(
            line_user_id,
            "申し訳ありません。リクエストの処理中にエラーが発生しました。後でもう一度お試しください。",
        )

    @pytest.mark.asyncio
    async def test_handle_scraping_error_dns_lookup_error(
        self, mock_send_push_message: AsyncMock
    ) -> None:
        """Test handling a DNS lookup error."""
        # Arrange
        line_user_id = "U1234567890abcdef1234567890abcdef"
        error = HTTPException(
            status_code=500, detail="DNSLookupError: DNS lookup failed"
        )

        # Act
        await handle_http_exception(error, line_user_id)

        # Assert
        mock_send_push_message.assert_called_once_with(
            line_user_id,
            "申し訳ありません。リクエストの処理中にエラーが発生しました。後でもう一度お試しください。",
        )

    @pytest.mark.asyncio
    async def test_handle_scraping_error_timeout_error(
        self, mock_send_push_message: AsyncMock
    ) -> None:
        """Test handling a timeout error."""
        # Arrange
        line_user_id = "U1234567890abcdef1234567890abcdef"
        error = HTTPException(status_code=500, detail="TimeoutError: Request timed out")

        # Act
        await handle_http_exception(error, line_user_id)

        # Assert
        mock_send_push_message.assert_called_once_with(
            line_user_id,
            "申し訳ありません。リクエストの処理中にエラーが発生しました。後でもう一度お試しください。",
        )

    @pytest.mark.asyncio
    async def test_handle_scraping_error_general_error(
        self, mock_send_push_message: AsyncMock
    ) -> None:
        """Test handling a general error."""
        # Arrange
        line_user_id = "U1234567890abcdef1234567890abcdef"
        error = HTTPException(status_code=500, detail="Some unexpected error occurred")

        # Act
        await handle_http_exception(error, line_user_id)

        # Assert
        mock_send_push_message.assert_called_once_with(
            line_user_id,
            "申し訳ありません。リクエストの処理中にエラーが発生しました。後でもう一度お試しください。",
        )

    @pytest.mark.asyncio
    async def test_handle_scraping_error_404(
        self, mock_send_push_message: AsyncMock
    ) -> None:
        """Test handling a 404 error."""
        # Arrange
        line_user_id = "U1234567890abcdef1234567890abcdef"
        error = HTTPException(status_code=404, detail="Property not found")

        # Act
        await handle_http_exception(error, line_user_id)

        # Assert
        mock_send_push_message.assert_called_once_with(
            line_user_id,
            "指定された物件は見つかりませんでした。URLが正しいか、または物件が削除されていないか確認してください。",
        )

    @pytest.mark.asyncio
    async def test_handle_scraping_error_403(
        self, mock_send_push_message: AsyncMock
    ) -> None:
        """Test handling a 403 error."""
        # Arrange
        line_user_id = "U1234567890abcdef1234567890abcdef"
        error = HTTPException(
            status_code=403, detail="HTTP Status Code: 403 - Forbidden"
        )

        # Act
        await handle_http_exception(error, line_user_id)

        # Assert
        mock_send_push_message.assert_called_once_with(
            line_user_id,
            "申し訳ありません。リクエストの処理中にエラーが発生しました。後でもう一度お試しください。",
        )

    @pytest.mark.asyncio
    async def test_handle_scraping_error_500(
        self, mock_send_push_message: AsyncMock
    ) -> None:
        """Test handling a 500 error."""
        # Arrange
        line_user_id = "U1234567890abcdef1234567890abcdef"
        error = HTTPException(
            status_code=500, detail="HTTP Status Code: 500 - Internal Server Error"
        )

        # Act
        await handle_http_exception(error, line_user_id)

        # Assert
        mock_send_push_message.assert_called_once_with(
            line_user_id,
            "申し訳ありません。リクエストの処理中にエラーが発生しました。後でもう一度お試しください。",
        )

    @pytest.mark.asyncio
    async def test_handle_scraping_error_http_error(
        self, mock_send_push_message: AsyncMock
    ) -> None:
        """Test handling an HTTP error."""
        # Arrange
        line_user_id = "U1234567890abcdef1234567890abcdef"
        error = HTTPException(
            status_code=500,
            detail="HttpError on https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/",
        )

        # Act
        await handle_http_exception(error, line_user_id)

        # Assert
        mock_send_push_message.assert_called_once_with(
            line_user_id,
            "申し訳ありません。リクエストの処理中にエラーが発生しました。後でもう一度お試しください。",
        )

    @pytest.mark.asyncio
    async def test_handle_scraping_error_property_name_not_found(
        self, mock_send_push_message: AsyncMock
    ) -> None:
        """Test handling a property name not found error."""
        # Arrange
        line_user_id = "U1234567890abcdef1234567890abcdef"
        error = HTTPException(
            status_code=404, detail="Property name not found in the scraped data"
        )

        # Act
        await handle_http_exception(error, line_user_id)

        # Assert
        mock_send_push_message.assert_called_once_with(
            line_user_id,
            "指定された物件は見つかりませんでした。URLが正しいか、または物件が削除されていないか確認してください。",
        )

    @pytest.mark.asyncio
    async def test_handle_scraping_error_validation_error(
        self, mock_send_push_message: AsyncMock
    ) -> None:
        """Test handling a validation error."""
        # Arrange
        line_user_id = "U1234567890abcdef1234567890abcdef"
        error = HTTPException(
            status_code=422, detail="ValidationError: Invalid data format"
        )

        # Act
        await handle_http_exception(error, line_user_id)

        # Assert
        mock_send_push_message.assert_called_once_with(
            line_user_id,
            "申し訳ありません。リクエストの処理中にエラーが発生しました。後でもう一度お試しください。",
        )


@pytest.mark.webhook
class TestSendPushMessage:
    """Tests for the send_push_message function."""

    @pytest.fixture
    def mock_api_client(self) -> Generator[MagicMock, None, None]:
        """Mock the LINE API client."""
        with patch("app.apis.webhooks.ApiClient") as mock:
            mock_instance = MagicMock()
            mock_instance.__enter__.return_value = mock_instance
            mock_instance.__exit__.return_value = None
            mock.return_value = mock_instance
            yield mock

    @pytest.fixture
    def mock_messaging_api(self) -> Generator[MagicMock, None, None]:
        """Mock the LINE messaging API."""
        with patch("app.apis.webhooks.MessagingApi") as mock:
            mock_instance = MagicMock()
            mock_instance.push_message_with_http_info = AsyncMock()
            mock.return_value = mock_instance
            yield mock

    @pytest.mark.asyncio
    async def test_send_push_message_success(
        self, mock_api_client: MagicMock, mock_messaging_api: MagicMock
    ) -> None:
        """Test successful push message sending."""
        # Arrange
        user_id = "test_user_id"
        message = "Test message"

        # Act
        await send_push_message(user_id, message)

        # Assert
        mock_api_client.assert_called_once()
        mock_messaging_api.assert_called_once()
        mock_messaging_api.return_value.push_message_with_http_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_push_message_exception(
        self, mock_api_client: MagicMock, mock_messaging_api: MagicMock
    ) -> None:
        """Test exception handling during push message sending."""
        # Arrange
        user_id = "test_user_id"
        message = "Test message"
        mock_messaging_api.return_value.push_message_with_http_info.side_effect = (
            Exception("Test exception")
        )

        # Act
        await send_push_message(user_id, message)

        # Assert
        mock_api_client.assert_called_once()
        mock_messaging_api.assert_called_once()
        mock_messaging_api.return_value.push_message_with_http_info.assert_called_once()


@pytest.mark.webhook
class TestIsValidPropertyUrlExtended:
    """Extended tests for the is_valid_property_url function."""

    def test_valid_suumo_ms_url_with_query_params(self) -> None:
        """Test validation of SUUMO mansion URL with query parameters."""
        # Arrange
        url = "https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/?page=2&sort=price"

        # Act
        result = is_valid_property_url(url)

        # Assert
        assert result is True

    def test_valid_suumo_ms_url_with_subdomain(self) -> None:
        """Test validation of SUUMO mansion URL with subdomain."""
        # Arrange
        url = "https://www.suumo.jp/ms/mansion/tokyo/sc_shinjuku/"

        # Act
        result = is_valid_property_url(url)

        # Assert
        assert result is True

    def test_valid_suumo_ms_url_with_property_id(self) -> None:
        """Test validation of SUUMO mansion URL with property ID."""
        # Arrange
        url = "https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/123456789/"

        # Act
        result = is_valid_property_url(url)

        # Assert
        assert result is True

    def test_invalid_suumo_url_wrong_path(self) -> None:
        """Test validation of SUUMO URL with wrong path."""
        # Arrange
        url = "https://suumo.jp/library/article/123456/"

        # Act
        result = is_valid_property_url(url)

        # Assert
        assert result is False


@pytest.mark.webhook
class TestExtractUrlsExtended:
    """Extended tests for the extract_urls function."""

    def test_extract_urls_with_japanese_text(self) -> None:
        """Test URL extraction from Japanese text."""
        # Arrange
        text = "東京の物件を見つけました: https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/ とても良い物件です！"

        # Act
        result = extract_urls(text)

        # Assert
        assert result == ["https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/"]

    def test_extract_urls_with_multiple_japanese_sentences(self) -> None:
        """Test URL extraction from multiple Japanese sentences."""
        # Arrange
        text = (
            "最初の物件: https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/\n"
            "二つ目の物件: https://suumo.jp/ms/mansion/tokyo/sc_shibuya/\n"
            "どちらが良いですか？"
        )

        # Act
        result = extract_urls(text)

        # Assert
        assert result == [
            "https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/",
            "https://suumo.jp/ms/mansion/tokyo/sc_shibuya/",
        ]

    def test_extract_urls_with_url_in_parentheses(self) -> None:
        """Test URL extraction when URL is in parentheses."""
        # Arrange
        text = "この物件を検討しています（https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/）どう思いますか？"

        # Act
        result = extract_urls(text)

        # Assert
        assert result == ["https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/"]

    def test_extract_urls_with_malformed_url(self) -> None:
        """Test URL extraction with malformed URL."""
        # Arrange
        text = "この物件を見てください: https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/ と http:/broken.url"

        # Act
        result = extract_urls(text)

        # Assert
        assert result == ["https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/"]


@pytest.mark.webhook
class TestWebhookMessageHandlerExtended:
    """Extended tests for the webhook_message_handler function."""

    @pytest.fixture
    def mock_request_with_events(self) -> MagicMock:
        """
        Create a mock Request object with valid signature and events.

        Returns:
            MagicMock: A mock of the FastAPI Request object with events
        """
        request = MagicMock(spec=Request)
        request.headers = {"X-Line-Signature": "valid_signature"}

        # Create a sample event payload with multiple events
        events = [
            {
                "type": "message",
                "message": {"type": "text", "id": "12345", "text": "Hello"},
                "timestamp": 1625665780000,
                "source": {"type": "user", "userId": "user1"},
                "replyToken": "reply1",
            },
            {
                "type": "follow",
                "timestamp": 1625665790000,
                "source": {"type": "user", "userId": "user2"},
                "replyToken": "reply2",
            },
        ]
        request.body.return_value = json.dumps({"events": events}).encode()
        return request

    @pytest.fixture
    def mock_handler_with_events(self) -> Generator[MagicMock, None, None]:
        """
        Mock the LINE webhook handler with event handling.

        Yields:
            MagicMock: A mock of the LINE webhook handler
        """
        with patch("app.apis.webhooks.line_handler") as mock_handler:
            # Configure the mock to properly handle events
            mock_handler.handle.return_value = None
            yield mock_handler

    @pytest.mark.asyncio
    async def test_webhook_message_handler_with_multiple_events(
        self, mock_request_with_events: MagicMock, mock_handler_with_events: MagicMock
    ) -> None:
        """Test webhook handler with multiple events."""
        # Act
        response = await webhook_message_handler(mock_request_with_events)

        # Assert
        assert response == WebhookResponse(message="Webhook message received!")
        mock_handler_with_events.handle.assert_called_once()
        # Just verify the handler was called with two arguments
        assert len(mock_handler_with_events.handle.call_args[0]) == 2


@pytest.mark.webhook
class TestIntegrationScenarios:
    """Integration tests for webhook scenarios."""

    @pytest.fixture
    def mock_event_with_property_url(self) -> MagicMock:
        """Create a mock event with a property URL."""
        event = MagicMock(spec=MessageEvent)
        event.reply_token = "test_reply_token"
        event.message = MagicMock(spec=TextMessageContent)
        event.message.text = "Check out this property: https://suumo.jp/ms/test/"
        event.source = MagicMock(spec=Source)
        event.source.user_id = "test_user_id"
        return event

    @pytest.fixture
    def mock_send_reply_integration(self) -> Generator[AsyncMock, None, None]:
        """Mock the send_reply function for integration tests."""
        with patch("app.apis.webhooks.send_reply", autospec=True) as mock:
            mock.return_value = None
            yield mock

    @pytest.fixture
    def mock_handle_scraping(self) -> Generator[AsyncMock, None, None]:
        """Mock the handle_scraping function for integration tests."""
        with patch("app.apis.webhooks.handle_scraping", autospec=True) as mock:
            mock.return_value = None
            # Configure the mock to ignore the collections parameter
            mock.side_effect = (
                lambda reply_token, url, line_user_id, collections=None: None
            )
            yield mock

    @pytest.mark.asyncio
    async def test_full_text_message_flow_with_property_url(
        self,
        mock_event_with_property_url: MagicMock,
        mock_send_reply_integration: AsyncMock,
        mock_handle_scraping: AsyncMock,
    ) -> None:
        """
        Test the full flow of processing a text message with a property URL.

        This test simulates the entire process from receiving a message event
        to handling the scraping process.
        """
        # Given: We need to mock the extract_urls and is_valid_property_url functions
        with (
            patch(
                "app.apis.webhooks.extract_urls",
                return_value=["https://suumo.jp/ms/test/"],
            ) as mock_extract_urls,
            patch(
                "app.apis.webhooks.is_valid_property_url", return_value=True
            ) as mock_is_valid_property_url,
            patch(
                "app.apis.webhooks.send_push_message", autospec=True
            ) as mock_send_push,
            patch(
                "app.apis.webhooks.get_database_collections",
                return_value=None,
            ),
        ):
            mock_send_push.return_value = None

            # When: We process the text message
            await process_text_message(mock_event_with_property_url)

            # Then: The URL extraction and validation functions should be called
            mock_extract_urls.assert_called_once_with(
                "Check out this property: https://suumo.jp/ms/test/"
            )
            mock_is_valid_property_url.assert_called_once_with(
                "https://suumo.jp/ms/test/"
            )

            # And: The handle_scraping function should be called with the correct parameters
            mock_handle_scraping.assert_called_once_with(
                "test_reply_token",
                "https://suumo.jp/ms/test/",
                "test_user_id",
                None,
            )

    @pytest.fixture
    def mock_event_with_multiple_urls(self) -> MagicMock:
        """Create a mock event with multiple URLs."""
        event = MagicMock(spec=MessageEvent)
        event.reply_token = "test_reply_token"
        event.message = MagicMock(spec=TextMessageContent)
        event.message.text = (
            "最初の物件: https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/\n"
            "二つ目の物件: https://suumo.jp/ms/mansion/tokyo/sc_shibuya/"
        )
        event.source = MagicMock(spec=Source)
        event.source.user_id = "test_user_id"
        return event

    @pytest.mark.asyncio
    async def test_text_message_with_multiple_urls(
        self,
        mock_event_with_multiple_urls: MagicMock,
        mock_send_reply_integration: AsyncMock,
    ) -> None:
        """Test handling a message with multiple URLs."""
        # Arrange
        urls = [
            "https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/",
            "https://suumo.jp/ms/mansion/tokyo/sc_shibuya/",
        ]

        with (
            patch(
                "app.apis.webhooks.extract_urls", return_value=urls
            ) as mock_extract_urls,
            patch(
                "app.apis.webhooks.is_valid_property_url", return_value=True
            ) as mock_is_valid,
            patch(
                "app.apis.webhooks.handle_scraping", autospec=True
            ) as mock_handle_scraping,
            patch(
                "app.apis.webhooks.get_database_collections",
                return_value=None,
            ),
        ):

            # Act
            await process_text_message(mock_event_with_multiple_urls)

            # Assert
            mock_extract_urls.assert_called_once_with(
                mock_event_with_multiple_urls.message.text
            )
            # Should only validate and process the first URL
            mock_is_valid.assert_called_once_with(urls[0])

            # The handle_scraping function should be called with the first URL
            mock_handle_scraping.assert_called_once_with(
                mock_event_with_multiple_urls.reply_token,
                urls[0],  # Only the first URL should be processed
                mock_event_with_multiple_urls.source.user_id,
                None,
            )


@pytest.mark.webhook
class TestHandleFollowEventExtended:
    """Extended tests for the handle_follow_event function."""

    @pytest.fixture
    def mock_follow_event(self) -> MagicMock:
        """Create a mock follow event."""
        mock = AsyncMock()
        mock.source = AsyncMock()
        mock.source.user_id = "test_user_id"
        mock.reply_token = "test_reply_token"
        return mock

    @pytest.fixture
    def mock_asyncio_create_task(self) -> Generator[MagicMock, None, None]:
        """Mock the asyncio.create_task function."""
        with patch("app.apis.webhooks.asyncio.create_task") as mock:
            yield mock

    def test_handle_follow_event_creates_task(
        self, mock_follow_event: MagicMock, mock_asyncio_create_task: MagicMock
    ) -> None:
        """Test that handle_follow_event creates an asyncio task."""
        # Act
        handle_follow_event(mock_follow_event)

        # Assert
        mock_asyncio_create_task.assert_called_once()
        # Verify the coroutine function passed to create_task
        coroutine_func = mock_asyncio_create_task.call_args[0][0]
        assert coroutine_func.cr_code.co_name == "process_follow_event"


@pytest.mark.webhook
class TestProcessFollowEventExtended:
    """Test the process_follow_event function."""

    @pytest.fixture
    def mock_follow_event(self) -> MagicMock:
        """Create a mock follow event."""
        mock_event = MagicMock()
        mock_event.source.user_id = "test_user_id"
        mock_event.type = "follow"
        return mock_event

    @pytest.fixture
    def mock_send_push_message(self) -> Generator[AsyncMock, None, None]:
        """Create a mock send_push_message function."""
        with patch("app.apis.webhooks.send_push_message") as mock:
            mock.return_value = None
            yield mock

    @pytest.fixture
    def mock_db(self) -> Generator[AsyncMock, None, None]:
        """Create a mock database collection."""
        mock = AsyncMock()
        mock.find_one.return_value = None
        mock.insert_one.return_value = AsyncMock()
        yield mock

    @pytest.fixture
    def mock_get_current_time(self) -> Generator[MagicMock, None, None]:
        """Mock the get_current_time function."""
        with patch("app.apis.webhooks.get_current_time") as mock:
            mock.return_value = datetime.now()
            yield mock

    @pytest.fixture
    def mock_os_getenv(self) -> Generator[MagicMock, None, None]:
        """Mock os.getenv to return a consistent collection name."""
        with patch("app.apis.webhooks.os.getenv") as mock:
            mock.return_value = "users"
            yield mock

    @pytest.mark.asyncio
    async def test_process_follow_event_new_user(
        self,
        mock_follow_event: MagicMock,
        mock_send_push_message: AsyncMock,
        mock_db: AsyncMock,
        mock_get_current_time: MagicMock,
        mock_os_getenv: MagicMock,
    ) -> None:
        """Test processing a follow event for a new user."""
        # Arrange
        # Simulate user not found in database
        mock_db.find_one.return_value = None
        mock_db.insert_one.return_value = AsyncMock()

        # Mock get_database_collections
        with patch(
            "app.apis.webhooks.get_database_collections"
        ) as mock_get_collections:
            mock_get_collections.return_value = (mock_db, AsyncMock(), AsyncMock())

            # Act
            await process_follow_event(mock_follow_event)

            # Assert
            # Check if database was queried for the user
            mock_db.find_one.assert_called_once_with(
                {"line_user_id": mock_follow_event.source.user_id}
            )
            # Verify welcome message was sent
            mock_send_push_message.assert_called_once_with(
                mock_follow_event.source.user_id,
                "ようこそ！マンションウォッチへ！\nSUUMOの物件URLを送っていただければ、情報を取得します。",
            )

    @pytest.mark.asyncio
    async def test_process_follow_event_existing_user(
        self,
        mock_follow_event: MagicMock,
        mock_send_push_message: AsyncMock,
        mock_db: AsyncMock,
        mock_get_current_time: MagicMock,
        mock_os_getenv: MagicMock,
    ) -> None:
        """Test processing a follow event for an existing user."""
        # Mock get_database_collections
        with patch(
            "app.apis.webhooks.get_database_collections"
        ) as mock_get_collections:
            # Arrange
            mock_users_collection = AsyncMock()
            mock_users_collection.find_one.return_value = {
                "line_user_id": mock_follow_event.source.user_id,
                "created_at": datetime.now(),
            }
            mock_get_collections.return_value = (
                mock_users_collection,
                MagicMock(),
                MagicMock(),
            )

            # Act
            await process_follow_event(mock_follow_event)

            # Assert
            # Check if database was queried for the user
            mock_users_collection.find_one.assert_called_once_with(
                {"line_user_id": mock_follow_event.source.user_id}
            )
            # Verify no welcome message was sent for existing user
            mock_send_push_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_follow_event_exception(
        self,
        mock_follow_event: MagicMock,
        mock_send_push_message: AsyncMock,
        mock_db: AsyncMock,
        mock_os_getenv: MagicMock,
    ) -> None:
        """Test handling an exception during follow event processing."""
        # Mock get_database_collections
        with patch(
            "app.apis.webhooks.get_database_collections"
        ) as mock_get_collections:
            # Arrange
            mock_users_collection = AsyncMock()
            mock_users_collection.find_one.side_effect = Exception("Test exception")
            mock_get_collections.return_value = (
                mock_users_collection,
                MagicMock(),
                MagicMock(),
            )

            # Act
            await process_follow_event(mock_follow_event)

            # Assert
            # Check if database was queried
            mock_users_collection.find_one.assert_called_once()
            # No message should be sent on exception
            mock_send_push_message.assert_not_called()
