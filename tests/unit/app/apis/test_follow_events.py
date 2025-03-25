"""Tests for the follow event handling in the webhooks API."""

from typing import Generator
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from linebot.v3.webhooks import FollowEvent, Source

from app.apis.webhooks import handle_follow_event, process_follow_event


@pytest.mark.webhook
class TestHandleFollowEvent:
    """Tests for the handle_follow_event function."""

    @pytest.fixture
    def mock_follow_event(self) -> MagicMock:
        """Create a mock follow event."""
        event = MagicMock(spec=FollowEvent)
        event.source = MagicMock(spec=Source)
        event.source.user_id = "test_user_id"
        event.reply_token = "test_reply_token"
        return event

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
class TestProcessFollowEvent:
    """Tests for the process_follow_event function."""

    @pytest.fixture
    def mock_follow_event(self) -> MagicMock:
        """Create a mock follow event."""
        event = MagicMock(spec=FollowEvent)
        event.source = MagicMock(spec=Source)
        event.source.user_id = "test_user_id"
        event.reply_token = "test_reply_token"
        return event

    @pytest.fixture
    def mock_send_push_message(self) -> Generator[AsyncMock, None, None]:
        """Mock the send_push_message function."""
        with patch("app.apis.webhooks.send_push_message", autospec=True) as mock:
            mock.return_value = None
            yield mock

    @pytest.fixture
    def mock_get_current_time(self) -> Generator[MagicMock, None, None]:
        """Mock the get_current_time function."""
        with patch("app.apis.webhooks.get_current_time") as mock:
            mock.return_value = "2023-01-01T00:00:00Z"
            yield mock

    @pytest.fixture
    def mock_get_db(self) -> Generator[AsyncMock, None, None]:
        """Mock the get_db function."""
        with patch("app.apis.webhooks.get_db") as mock:
            mock_db = MagicMock()
            mock_collection = AsyncMock()
            mock_db.__getitem__.return_value = mock_collection
            mock.return_value = mock_db
            yield mock, mock_collection

    @pytest.mark.asyncio
    async def test_process_follow_event_new_user(
        self,
        mock_follow_event: MagicMock,
        mock_send_push_message: AsyncMock,
        mock_get_current_time: MagicMock,
        mock_get_db: tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test processing a follow event for a new user."""
        # Arrange
        _, mock_collection = mock_get_db
        mock_collection.find_one.return_value = None  # User doesn't exist

        # Act
        await process_follow_event(mock_follow_event)

        # Assert
        # Check if database was queried for the user twice
        # Once in process_follow_event and once in create_or_update_user
        assert mock_collection.find_one.call_count == 2
        mock_collection.find_one.assert_has_calls(
            [
                call({"line_user_id": mock_follow_event.source.user_id}),
                call({"line_user_id": mock_follow_event.source.user_id}),
            ]
        )

        # Check if new user was inserted
        mock_collection.insert_one.assert_called_once()
        insert_call = mock_collection.insert_one.call_args[0][0]
        assert insert_call["line_user_id"] == mock_follow_event.source.user_id

        # Check if welcome message was sent
        mock_send_push_message.assert_called_once_with(
            mock_follow_event.source.user_id,
            "ようこそ！マンションウォッチへ！\nSUUMOの物件URLを送っていただければ、情報を取得します。",
        )

    @pytest.mark.asyncio
    async def test_process_follow_event_existing_user(
        self,
        mock_follow_event: MagicMock,
        mock_send_push_message: AsyncMock,
        mock_get_current_time: MagicMock,
        mock_get_db: tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test processing a follow event for an existing user."""
        # Arrange
        _, mock_collection = mock_get_db
        mock_collection.find_one.return_value = {
            "line_user_id": mock_follow_event.source.user_id
        }  # User exists

        # Act
        await process_follow_event(mock_follow_event)

        # Assert
        # Check if database was queried for the user twice
        # Once in process_follow_event and once in create_or_update_user
        assert mock_collection.find_one.call_count == 2
        mock_collection.find_one.assert_has_calls(
            [
                call({"line_user_id": mock_follow_event.source.user_id}),
                call({"line_user_id": mock_follow_event.source.user_id}),
            ]
        )

        # Check that no new user was inserted
        mock_collection.insert_one.assert_not_called()

        # Check that no welcome message was sent
        mock_send_push_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_follow_event_exception(
        self,
        mock_follow_event: MagicMock,
        mock_send_push_message: AsyncMock,
        mock_get_db: tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test handling an exception during follow event processing."""
        # Arrange
        _, mock_collection = mock_get_db
        mock_collection.find_one.side_effect = Exception("Test exception")

        # Act
        await process_follow_event(mock_follow_event)

        # Assert
        mock_collection.find_one.assert_called_once_with(
            {"line_user_id": mock_follow_event.source.user_id}
        )
        # No error message is sent in the exception case
        mock_send_push_message.assert_not_called()
