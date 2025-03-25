import asyncio
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request, status
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import FollowEvent, MessageEvent, Source, TextMessageContent

from app.apis.webhooks import (
    PropertyStatus,
    extract_urls,
    get_property_status,
    handle_follow_event,
    handle_scraping,
    handle_text_message,
    is_valid_property_url,
    process_follow_event,
    process_text_message,
    send_reply,
    webhook_message_handler,
)
from app.models.apis.webhook import WebhookResponse


@pytest.mark.webhook
class TestWebhookMessageHandler:
    """Tests for the webhook_message_handler function."""

    @pytest.fixture
    def mock_request(self) -> MagicMock:
        """
        Create a mock Request object with valid signature and empty events.

        Returns:
            MagicMock: A mock of the FastAPI Request object
        """
        request = MagicMock(spec=Request)
        request.headers = {"X-Line-Signature": "valid_signature"}
        request.body.return_value = b'{"events": []}'
        return request

    @pytest.fixture
    def mock_line_handler(self) -> Generator[MagicMock, None, None]:
        """
        Mock the LINE webhook handler.

        Yields:
            MagicMock: A mock of the LINE webhook handler
        """
        with patch("app.apis.webhooks.line_handler") as mock_line_handler:
            yield mock_line_handler

    @pytest.mark.asyncio
    async def test_webhook_message_handler_success(
        self, mock_request: MagicMock, mock_line_handler: MagicMock
    ) -> None:
        """
        Test successful webhook handling.

        The handler should process the request and return a successful response.

        Args:
            mock_request: Mock Request object
            mock_line_handler: Mock LINE webhook handler
        """
        # When: We call the webhook handler with a valid request
        response = await webhook_message_handler(mock_request)

        # Then: The handler should be called with the correct parameters
        mock_line_handler.handle.assert_called_once_with(
            '{"events": []}', "valid_signature"
        )

        # And: The response should be a WebhookResponse with the expected message
        assert isinstance(response, WebhookResponse)
        assert response.message == "Webhook message received!"

    @pytest.mark.asyncio
    async def test_webhook_message_handler_missing_signature(
        self, mock_request: MagicMock
    ) -> None:
        """
        Test handling of a request with missing signature header.

        The handler should raise an HTTPException with a 400 status code.

        Args:
            mock_request: Mock Request object
        """
        # Given: A request without a signature header
        mock_request.headers = {}

        # When/Then: Calling the webhook handler should raise an HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await webhook_message_handler(mock_request)

        # And: The exception should have the correct status code
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == "Missing signature header"

    async def test_webhook_message_handler_invalid_signature(
        self, mock_request, mock_line_handler
    ):
        # Test invalid signature
        mock_line_handler.handle.side_effect = InvalidSignatureError(
            "Invalid signature"
        )

        with pytest.raises(HTTPException) as exc_info:
            await webhook_message_handler(mock_request)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == "Invalid signature"

    async def test_webhook_message_handler_general_exception(
        self, mock_request, mock_line_handler
    ):
        # Test general exception handling
        mock_line_handler.handle.side_effect = Exception("General error")

        with pytest.raises(HTTPException) as exc_info:
            await webhook_message_handler(mock_request)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Error processing webhook"


@pytest.mark.webhook
class TestExtractUrls:
    """Tests for the extract_urls function."""

    def test_extract_urls_single_url(self) -> None:
        """
        Test extracting a single URL from a message.

        The function should correctly identify and extract a single URL.
        """
        # Given: A message with a single URL
        message = "Check out this property: https://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856419/"

        # When: We extract URLs from the message
        urls = extract_urls(message)

        # Then: The function should return a list with the single URL
        assert len(urls) == 1
        assert (
            urls[0]
            == "https://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856419/"
        )

    def test_extract_urls_multiple_urls(self) -> None:
        """
        Test extracting multiple URLs from a message.

        The function should correctly identify and extract all URLs in the message.
        """
        # Given: A message with multiple URLs
        message = (
            "Check these properties: https://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856419/ "
            "and https://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856420/"
        )

        # When: We extract URLs from the message
        urls = extract_urls(message)

        # Then: The function should return a list with both URLs
        assert len(urls) == 2
        assert (
            urls[0]
            == "https://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856419/"
        )
        assert (
            urls[1]
            == "https://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856420/"
        )

    def test_extract_urls_no_urls(self) -> None:
        """
        Test extracting URLs from a message with no URLs.

        The function should return an empty list when no URLs are present.
        """
        # Given: A message with no URLs
        message = "This message has no URLs"

        # When: We extract URLs from the message
        urls = extract_urls(message)

        # Then: The function should return an empty list
        assert len(urls) == 0

    def test_extract_urls_with_query_params(self) -> None:
        """
        Test extracting URLs with query parameters.

        The function should correctly extract URLs that include query parameters.
        """
        # Given: A message with a URL that includes query parameters
        message = (
            "Check this property: https://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856419/"
            "?key1=value1&key2=value2"
        )

        # When: We extract URLs from the message
        urls = extract_urls(message)

        # Then: The function should return a list with the URL including query parameters
        assert len(urls) == 1
        assert (
            urls[0]
            == "https://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856419/?key1=value1&key2=value2"
        )

    def test_extract_urls_with_property_name_and_url(self) -> None:
        """
        Test extracting URLs from a message with property name and URL.

        The function should correctly extract URLs even when they're part of a property name.
        """
        # Given: A message with a property name and URL
        message = "コスギサードアヴェニューザ・レジデンス\nhttps://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856419/\nby SUUMO"

        # When: We extract URLs from the message
        urls = extract_urls(message)

        # Then: The function should return a list with the URL
        assert len(urls) == 1
        assert (
            urls[0]
            == "https://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856419/"
        )


class TestIsValidPropertyUrl:
    def test_valid_suumo_url(self):
        url = "https://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856419/"
        assert is_valid_property_url(url) is True

    def test_invalid_domain_url(self):
        url = "https://example.com/property/123"
        assert is_valid_property_url(url) is False

    def test_subdomain_suumo_url(self):
        url = (
            "https://sub.suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856419/"
        )
        assert is_valid_property_url(url) is True

    def test_valid_suumo_ms_chuko_url(self):
        """Test validation of a SUUMO URL with ms/chuko format."""
        url = "https://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856419/"
        assert is_valid_property_url(url) is True


class TestSendReply:
    @pytest.fixture
    def mock_api_client(self) -> Generator[MagicMock, None, None]:
        """
        Mock the ApiClient class.

        Returns:
            Generator[MagicMock, None, None]: A mock of the ApiClient
        """
        with patch("app.apis.webhooks.ApiClient") as mock_api_client:
            mock_instance = MagicMock()
            mock_api_client.return_value.__enter__.return_value = mock_instance
            yield mock_api_client

    @pytest.fixture
    def mock_messaging_api(self) -> Generator[MagicMock, None, None]:
        """
        Mock the MessagingApi class.

        Returns:
            Generator[MagicMock, None, None]: A mock of the MessagingApi
        """
        with patch("app.apis.webhooks.MessagingApi") as mock_messaging_api:
            mock_instance = MagicMock()
            mock_messaging_api.return_value = mock_instance
            yield mock_messaging_api

    async def test_send_reply_success(self, mock_api_client, mock_messaging_api):
        reply_token = "test_reply_token"
        message = "Test message"

        await send_reply(reply_token, message)

        # Check that MessagingApi was instantiated with the API client
        mock_messaging_api.assert_called_once()

        # Check that reply_message_with_http_info was called with the correct parameters
        mock_messaging_api.return_value.reply_message_with_http_info.assert_called_once()
        call_args = (
            mock_messaging_api.return_value.reply_message_with_http_info.call_args[0][0]
        )
        assert call_args.reply_token == reply_token
        assert len(call_args.messages) == 1
        assert call_args.messages[0].text == message
        assert call_args.messages[0].type == "text"

    async def test_send_reply_exception(self, mock_api_client, mock_messaging_api):
        # Set up the mock to raise an exception
        mock_messaging_api.return_value.reply_message_with_http_info.side_effect = (
            Exception("API error")
        )

        # The function should not raise an exception, it should log the error
        await send_reply("test_token", "Test message")

        # Verify the exception was handled
        mock_messaging_api.return_value.reply_message_with_http_info.assert_called_once()


@pytest.mark.webhook
class TestProcessTextMessage:
    """Tests for the process_text_message function."""

    @pytest.fixture
    def mock_event(self) -> MagicMock:
        """
        Create a mock MessageEvent with a property URL.

        Returns:
            MagicMock: A mock of the MessageEvent
        """
        event = MagicMock(spec=MessageEvent)
        event.message = MagicMock(spec=TextMessageContent)
        event.message.text = "Check this property: https://suumo.jp/ms/chuko/tokyo/sc_meguro/nc_75709932/"
        event.source = MagicMock(spec=Source)
        event.source.user_id = "test_user_id"
        event.reply_token = "test_reply_token"
        return event

    @pytest.fixture
    def mock_collections(self) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
        """Mock database collections."""
        return (AsyncMock(), AsyncMock(), AsyncMock())

    @pytest.fixture
    def mock_get_database_collections(self, mock_collections) -> AsyncMock:
        """Mock get_database_collections."""
        mock_get_db = AsyncMock()
        mock_get_db.return_value = mock_collections
        return mock_get_db

    @pytest.mark.asyncio
    async def test_process_text_message_with_valid_url(
        self,
        mock_event: MagicMock,
        mock_collections: tuple[AsyncMock, AsyncMock, AsyncMock],
    ) -> None:
        """
        Test processing a message with a valid property URL.

        The function should extract the URL, validate it, and start the scraping process.

        Args:
            mock_event: Mock MessageEvent
            mock_collections: Mock database collections
        """
        with (
            patch(
                "app.apis.webhooks.extract_suumo_url",
                return_value="https://suumo.jp/ms/chuko/tokyo/sc_meguro/nc_75709932/",
            ),
            patch("app.apis.webhooks.handle_scraping") as mock_handle_scraping,
            patch(
                "app.apis.webhooks.get_database_collections",
                return_value=mock_collections,
            ),
        ):
            mock_handle_scraping.return_value = asyncio.Future()
            mock_handle_scraping.return_value.set_result(None)

            await process_text_message(mock_event)

            mock_handle_scraping.assert_called_once_with(
                "test_reply_token",
                "https://suumo.jp/ms/chuko/tokyo/sc_meguro/nc_75709932/",
                "test_user_id",
                mock_collections,
            )

    @pytest.mark.asyncio
    async def test_process_text_message_with_property_name_and_url(
        self,
        mock_collections: tuple[AsyncMock, AsyncMock, AsyncMock],
    ) -> None:
        """
        Test processing a message with a property name and URL.

        The function should extract the URL from a message that includes a property name.

        Args:
            mock_collections: Mock database collections
        """
        event = MagicMock(spec=MessageEvent)
        event.message = MagicMock(spec=TextMessageContent)
        event.message.text = "コスギサードアヴェニューザ・レジデンス\nhttps://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856419/\nby SUUMO"
        event.source = MagicMock(spec=Source)
        event.source.user_id = "test_user_id"
        event.reply_token = "test_reply_token"

        with (
            patch("app.apis.webhooks.handle_scraping") as mock_handle_scraping,
            patch(
                "app.apis.webhooks.get_database_collections",
                return_value=mock_collections,
            ),
        ):
            mock_handle_scraping.return_value = asyncio.Future()
            mock_handle_scraping.return_value.set_result(None)

            await process_text_message(event)

            mock_handle_scraping.assert_called_once_with(
                "test_reply_token",
                "https://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_76856419/",
                "test_user_id",
                mock_collections,
            )


class TestHandleTextMessage:
    @pytest.fixture
    def mock_event(self) -> MagicMock:
        """
        Create a mock MessageEvent.

        Returns:
            MagicMock: A mock of the MessageEvent
        """
        event = MagicMock(spec=MessageEvent)
        return event

    @pytest.fixture
    def mock_process_text_message(self) -> Generator[AsyncMock, None, None]:
        """
        Mock the process_text_message function.

        Returns:
            Generator[AsyncMock, None, None]: A mock of the process_text_message function
        """
        with patch("app.apis.webhooks.process_text_message") as mock_process:
            yield mock_process

    @pytest.fixture
    def mock_create_task(self) -> Generator[AsyncMock, None, None]:
        """
        Mock the asyncio.create_task function.

        Returns:
            Generator[AsyncMock, None, None]: A mock of the create_task function
        """
        with patch("asyncio.create_task") as mock_create_task:
            # Create a mock coroutine
            mock_coro = AsyncMock()
            mock_create_task.return_value = mock_coro
            yield mock_create_task

    def test_handle_text_message(
        self, mock_event, mock_process_text_message, mock_create_task
    ):
        handle_text_message(mock_event)

        # Check that create_task was called
        mock_create_task.assert_called_once()
        # Check that process_text_message was called with the event
        mock_process_text_message.assert_called_once_with(mock_event)


class TestProcessFollowEvent:
    @pytest.fixture
    def mock_event(self) -> MagicMock:
        """
        Create a mock FollowEvent.

        Returns:
            MagicMock: A mock of the FollowEvent
        """
        event = MagicMock(spec=FollowEvent)
        event.source = MagicMock(spec=Source)
        event.source.user_id = "test_user_id"
        return event

    @pytest.fixture
    def mock_collections(self) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
        """Mock database collections."""
        return (AsyncMock(), AsyncMock(), AsyncMock())

    @pytest.mark.asyncio
    async def test_process_follow_event_new_user(
        self,
        mock_event: MagicMock,
        mock_collections: tuple[AsyncMock, AsyncMock, AsyncMock],
    ) -> None:
        """Test processing a new user follow event."""
        _, _, users_collection = mock_collections
        users_collection.find_one.return_value = None

        with patch(
            "app.apis.webhooks.get_database_collections", return_value=mock_collections
        ):
            await process_follow_event(mock_event)

            users_collection.find_one.assert_called_once_with(
                {"line_user_id": "test_user_id"}
            )

    @pytest.mark.asyncio
    async def test_process_follow_event_existing_user(
        self,
        mock_event: MagicMock,
        mock_collections: tuple[AsyncMock, AsyncMock, AsyncMock],
    ) -> None:
        """Test processing an existing user follow event."""
        _, _, users_collection = mock_collections
        users_collection.find_one.return_value = {
            "line_user_id": "test_user_id",
            "created_at": "2022-01-01T00:00:00Z",
            "updated_at": "2022-01-01T00:00:00Z",
        }

        with patch(
            "app.apis.webhooks.get_database_collections", return_value=mock_collections
        ):
            await process_follow_event(mock_event)

            users_collection.find_one.assert_called_once_with(
                {"line_user_id": "test_user_id"}
            )

    @pytest.mark.asyncio
    async def test_process_follow_event_exception(
        self,
        mock_event: MagicMock,
        mock_collections: tuple[AsyncMock, AsyncMock, AsyncMock],
    ) -> None:
        """Test handling exceptions during follow event processing."""
        _, _, users_collection = mock_collections
        users_collection.find_one.side_effect = Exception("Database error")

        with patch(
            "app.apis.webhooks.get_database_collections", return_value=mock_collections
        ):
            await process_follow_event(mock_event)
            users_collection.find_one.assert_called_once()


class TestHandleFollowEvent:
    @pytest.fixture
    def mock_event(self) -> MagicMock:
        """
        Create a mock FollowEvent.

        Returns:
            MagicMock: A mock of the FollowEvent
        """
        event = MagicMock(spec=FollowEvent)
        event.source = MagicMock(spec=Source)
        event.source.user_id = "test_user_id"
        return event

    @pytest.fixture
    def mock_process_follow_event(self) -> Generator[AsyncMock, None, None]:
        """
        Mock the process_follow_event function.

        Returns:
            Generator[AsyncMock, None, None]: A mock of the process_follow_event function
        """
        with patch("app.apis.webhooks.process_follow_event") as mock_process:
            yield mock_process

    @pytest.fixture
    def mock_create_task(self) -> Generator[MagicMock, None, None]:
        """
        Mock the asyncio.create_task function.

        Returns:
            Generator[MagicMock, None, None]: A mock of the asyncio.create_task function
        """
        with patch("asyncio.create_task") as mock_create_task:
            # Create a mock coroutine
            mock_coro = AsyncMock()
            mock_create_task.return_value = mock_coro
            yield mock_create_task

    def test_handle_follow_event(
        self, mock_event, mock_process_follow_event, mock_create_task
    ):
        handle_follow_event(mock_event)

        # Check that create_task was called
        mock_create_task.assert_called_once()
        # Check that process_follow_event was called with the event
        mock_process_follow_event.assert_called_once_with(mock_event)


@pytest.mark.webhook
class TestPropertyStatus:
    """Tests for PropertyStatus functionality."""

    def test_property_status_creation(self):
        """Test creating PropertyStatus with different parameters."""
        # Test with minimal parameters
        status = PropertyStatus(exists=False, user_has_access=False)
        assert status.exists is False
        assert status.user_has_access is False
        assert status.property_id is None

        # Test with all parameters
        status = PropertyStatus(exists=True, user_has_access=True, property_id="123")
        assert status.exists is True
        assert status.user_has_access is True
        assert status.property_id == "123"


@pytest.mark.webhook
class TestGetPropertyStatus:
    """Tests for the get_property_status function."""

    @pytest.fixture
    def mock_collections(self) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
        """Mock database collections."""
        return (AsyncMock(), AsyncMock(), AsyncMock())

    @pytest.mark.asyncio
    async def test_property_not_found(
        self,
        mock_collections: tuple[AsyncMock, AsyncMock, AsyncMock],
    ) -> None:
        """Test when property is not found in database."""
        properties_collection, _, _ = mock_collections
        properties_collection.find_one.return_value = None

        with patch(
            "app.apis.webhooks.get_database_collections", return_value=mock_collections
        ):
            status = await get_property_status(
                "test_url", "test_user", mock_collections
            )

            assert status.exists is False
            assert status.user_has_access is False
            assert status.property_id is None

    @pytest.mark.asyncio
    async def test_property_exists_user_has_access(
        self,
        mock_collections: tuple[AsyncMock, AsyncMock, AsyncMock],
    ) -> None:
        """Test when property exists and user has access."""
        properties_collection, user_properties_collection, _ = mock_collections
        properties_collection.find_one.return_value = {"_id": "123", "url": "test_url"}
        user_properties_collection.find_one.return_value = {"property_id": "123"}

        with patch(
            "app.apis.webhooks.get_database_collections", return_value=mock_collections
        ):
            status = await get_property_status(
                "test_url", "test_user", mock_collections
            )

            assert status.exists is True
            assert status.user_has_access is True
            assert status.property_id == "123"

    @pytest.mark.asyncio
    async def test_property_exists_user_no_access(
        self,
        mock_collections: tuple[AsyncMock, AsyncMock, AsyncMock],
    ) -> None:
        """Test when property exists but user doesn't have access."""
        properties_collection, user_properties_collection, _ = mock_collections
        properties_collection.find_one.return_value = {"_id": "123", "url": "test_url"}
        user_properties_collection.find_one.return_value = None

        with patch(
            "app.apis.webhooks.get_database_collections", return_value=mock_collections
        ):
            status = await get_property_status(
                "test_url", "test_user", mock_collections
            )

            assert status.exists is True
            assert status.user_has_access is False
            assert status.property_id == "123"


@pytest.mark.webhook
class TestHandleScraping:
    """Test cases for handle_scraping function."""

    @pytest.fixture
    def mock_send_reply(self):
        """Create a mock for send_reply function."""
        return AsyncMock()

    @pytest.fixture
    def mock_queue_scraping(self):
        """Create a mock for queue_scraping function."""
        return AsyncMock()

    @pytest.fixture
    def mock_get_property_status(self):
        """Create a mock for get_property_status function."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_error_handling(
        self,
        mock_send_reply,
        mock_queue_scraping,
        mock_get_property_status,
    ):
        """Test error handling in handle_scraping."""
        # Arrange
        reply_token = "test_reply_token"
        url = "https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/"
        line_user_id = "test_user"

        # Configure the mock to raise an exception on the second call
        mock_send_reply.side_effect = [None, Exception("Test error")]

        # We need to mock send_push_message
        with patch(
            "app.apis.webhooks.send_push_message", autospec=True
        ) as mock_send_push:
            mock_send_push.return_value = None

            # Also mock the general exception in queue_scraping
            mock_queue_scraping.side_effect = Exception("Test error")

            # Act
            await handle_scraping(reply_token, url, line_user_id)

            # Assert
            mock_send_push.assert_called_once_with(
                line_user_id,
                "申し訳ありません。リクエストの処理中にエラーが発生しました。後でもう一度お試しください。",
            )
