"""Tests for message handling functionality in the LINE bot."""

from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from linebot.v3.webhooks import MessageEvent, Source, TextMessageContent

from app.apis.webhooks import (
    find_valid_suumo_url,
    get_message_info,
    handle_message_error,
    is_valid_message_event,
    process_text_message,
    send_inquiry_response,
    send_invalid_url_response,
)


@pytest.fixture
def mock_event() -> MagicMock:
    """Create a mock MessageEvent for testing."""
    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=TextMessageContent)
    event.source = MagicMock(spec=Source)
    event.source.user_id = "test_user_id"
    event.reply_token = "test_reply_token"
    return event


@pytest.fixture
def mock_send_reply() -> Generator[AsyncMock, None, None]:
    """Mock the send_reply function."""
    with patch("app.apis.webhooks.send_reply", autospec=True) as mock:
        mock.return_value = None
        yield mock


@pytest.fixture
def mock_send_push() -> Generator[AsyncMock, None, None]:
    """Mock the send_push_message function."""
    with patch("app.apis.webhooks.send_push_message", autospec=True) as mock:
        mock.return_value = None
        yield mock


@pytest.fixture
def mock_handle_scraping() -> Generator[AsyncMock, None, None]:
    """Mock the handle_scraping function."""
    with patch("app.apis.webhooks.handle_scraping", autospec=True) as mock:
        mock.return_value = None
        yield mock


class TestIsValidMessageEvent:
    """Tests for the is_valid_message_event function."""

    def test_valid_event(self, mock_event: MagicMock) -> None:
        """Test a valid message event."""
        assert is_valid_message_event(mock_event) is True

    def test_event_without_message(self, mock_event: MagicMock) -> None:
        """Test an event without a message."""
        mock_event.message = None
        assert is_valid_message_event(mock_event) is False

    def test_event_without_source(self, mock_event: MagicMock) -> None:
        """Test an event without a source."""
        mock_event.source = None
        assert is_valid_message_event(mock_event) is False

    def test_event_without_user_id(self, mock_event: MagicMock) -> None:
        """Test an event without a user_id."""
        delattr(mock_event.source, "user_id")
        assert is_valid_message_event(mock_event) is False

    def test_event_without_reply_token(self, mock_event: MagicMock) -> None:
        """Test an event without a reply token."""
        mock_event.reply_token = None
        assert is_valid_message_event(mock_event) is False


class TestGetMessageInfo:
    """Tests for the get_message_info function."""

    def test_get_message_info(self, mock_event: MagicMock) -> None:
        """Test extracting message information."""
        mock_event.message.text = "Test message"
        mock_event.source.user_id = "test_user_id"
        mock_event.reply_token = "test_reply_token"

        message_text, user_id, reply_token = get_message_info(mock_event)
        assert message_text == "Test message"
        assert user_id == "test_user_id"
        assert reply_token == "test_reply_token"


class TestSendResponses:
    """Tests for the message response functions."""

    @pytest.mark.asyncio
    async def test_send_inquiry_response(self, mock_send_reply: AsyncMock) -> None:
        """Test sending the inquiry response message."""
        await send_inquiry_response("test_reply_token")
        mock_send_reply.assert_called_once_with(
            "test_reply_token",
            "お問い合わせありがとうございます！\n"
            "SUUMOの物件URLを送っていただければ、情報を取得いたします。",
        )

    @pytest.mark.asyncio
    async def test_send_invalid_url_response(self, mock_send_reply: AsyncMock) -> None:
        """Test sending the invalid URL response message."""
        await send_invalid_url_response("test_reply_token")
        mock_send_reply.assert_called_once_with(
            "test_reply_token",
            "SUUMOの物件ページURLを送信してください",
        )


class TestFindValidSuumoUrl:
    """Tests for the find_valid_suumo_url function."""

    def test_valid_suumo_url(self) -> None:
        """Test finding a valid SUUMO URL."""
        urls = [
            "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_123456/",
            "https://example.com/property/123",
        ]
        result = find_valid_suumo_url(urls)
        assert result == "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_123456/"

    def test_no_valid_suumo_url(self) -> None:
        """Test when no valid SUUMO URL is found."""
        urls = [
            "https://example.com/property/123",
            "https://homes.co.jp/property/456",
        ]
        result = find_valid_suumo_url(urls)
        assert result is None

    def test_empty_url_list(self) -> None:
        """Test with an empty URL list."""
        result = find_valid_suumo_url([])
        assert result is None

    def test_multiple_valid_suumo_urls(self) -> None:
        """Test with multiple valid SUUMO URLs (should return first one)."""
        urls = [
            "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_123456/",
            "https://suumo.jp/ms/chuko/tokyo/sc_shibuya/nc_789012/",
            "https://example.com/property/123",
        ]
        result = find_valid_suumo_url(urls)
        assert result == "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_123456/"


class TestHandleMessageError:
    """Tests for the handle_message_error function."""

    @pytest.mark.asyncio
    async def test_handle_message_error_with_reply_token(
        self, mock_event: MagicMock, mock_send_reply: AsyncMock
    ) -> None:
        """Test error handling with a valid reply token."""
        error = Exception("Test error")
        await handle_message_error(mock_event, error)
        mock_send_reply.assert_called_once_with(
            "test_reply_token",
            "申し訳ありません。メッセージの処理中にエラーが発生しました。",
        )

    @pytest.mark.asyncio
    async def test_handle_message_error_without_reply_token(
        self, mock_event: MagicMock, mock_send_push: AsyncMock
    ) -> None:
        """Test error handling when reply token is not available."""
        mock_event.reply_token = None
        error = Exception("Test error")
        await handle_message_error(mock_event, error)
        mock_send_push.assert_called_once_with(
            "test_user_id",
            "申し訳ありません。メッセージの処理中にエラーが発生しました。",
        )

    @pytest.mark.asyncio
    async def test_handle_message_error_with_invalid_event(
        self,
        mock_event: MagicMock,
        mock_send_reply: AsyncMock,
        mock_send_push: AsyncMock,
    ) -> None:
        """Test error handling with an invalid event."""
        mock_event.message = None
        error = Exception("Test error")
        await handle_message_error(mock_event, error)
        mock_send_reply.assert_not_called()
        mock_send_push.assert_not_called()


class TestProcessTextMessage:
    """Tests for the process_text_message function."""

    @pytest.mark.asyncio
    async def test_process_text_message_with_valid_url(
        self,
        mock_event: MagicMock,
        mock_send_reply: AsyncMock,
        mock_handle_scraping: AsyncMock,
    ) -> None:
        """Test processing a message with a valid SUUMO URL."""
        # Arrange
        mock_event.message.text = "Check this property: https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_123456/"
        with patch(
            "app.apis.webhooks.extract_urls",
            return_value=["https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_123456/"],
        ):
            # Act
            await process_text_message(mock_event)
            # Assert
            mock_handle_scraping.assert_called_once_with(
                "test_reply_token",
                "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_123456/",
                "test_user_id",
            )

    @pytest.mark.asyncio
    async def test_process_text_message_with_invalid_url(
        self,
        mock_event: MagicMock,
        mock_send_reply: AsyncMock,
        mock_handle_scraping: AsyncMock,
    ) -> None:
        """Test processing a message with an invalid URL."""
        # Arrange
        mock_event.message.text = (
            "Check this property: https://example.com/property/123"
        )
        with patch(
            "app.apis.webhooks.extract_urls",
            return_value=["https://example.com/property/123"],
        ):
            # Act
            await process_text_message(mock_event)
            # Assert
            mock_send_reply.assert_called_once_with(
                "test_reply_token",
                "SUUMOの物件ページURLを送信してください",
            )
            mock_handle_scraping.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_text_message_without_url(
        self,
        mock_event: MagicMock,
        mock_send_reply: AsyncMock,
        mock_handle_scraping: AsyncMock,
    ) -> None:
        """Test processing a message without any URL."""
        # Arrange
        mock_event.message.text = "Hello, I have a question about properties."
        with patch("app.apis.webhooks.extract_urls", return_value=[]):
            # Act
            await process_text_message(mock_event)
            # Assert
            mock_send_reply.assert_called_once_with(
                "test_reply_token",
                "お問い合わせありがとうございます！\n"
                "SUUMOの物件URLを送っていただければ、情報を取得いたします。",
            )
            mock_handle_scraping.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_text_message_with_invalid_event(
        self,
        mock_event: MagicMock,
        mock_send_reply: AsyncMock,
        mock_handle_scraping: AsyncMock,
    ) -> None:
        """Test processing an invalid event."""
        # Arrange
        mock_event.message = None
        # Act
        await process_text_message(mock_event)
        # Assert
        mock_send_reply.assert_not_called()
        mock_handle_scraping.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_text_message_with_multiple_urls(
        self,
        mock_event: MagicMock,
        mock_send_reply: AsyncMock,
        mock_handle_scraping: AsyncMock,
    ) -> None:
        """Test processing a message with multiple URLs."""
        # Arrange
        mock_event.message.text = (
            "Check these properties:\n"
            "1. https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_123456/\n"
            "2. https://example.com/property/123"
        )
        with patch(
            "app.apis.webhooks.extract_urls",
            return_value=[
                "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_123456/",
                "https://example.com/property/123",
            ],
        ):
            # Act
            await process_text_message(mock_event)
            # Assert
            mock_handle_scraping.assert_called_once_with(
                "test_reply_token",
                "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_123456/",
                "test_user_id",
            )

    @pytest.mark.asyncio
    async def test_process_text_message_with_error(
        self,
        mock_event: MagicMock,
        mock_send_reply: AsyncMock,
        mock_handle_scraping: AsyncMock,
    ) -> None:
        """Test processing a message that raises an error."""
        # Arrange
        mock_event.message.text = "Test message"
        with patch(
            "app.apis.webhooks.extract_urls", side_effect=Exception("Test error")
        ):
            # Act
            await process_text_message(mock_event)
            # Assert
            mock_send_reply.assert_called_once_with(
                "test_reply_token",
                "申し訳ありません。メッセージの処理中にエラーが発生しました。",
            )
            mock_handle_scraping.assert_not_called()
