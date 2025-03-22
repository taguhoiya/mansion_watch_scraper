"""Test module for MongoDB performance monitoring."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.monitoring import (
    PerformanceCommandListener,
    analyze_query_performance,
    get_collection_stats,
    monitor_performance,
)


class TestPerformanceMonitoring:
    """Test cases for performance monitoring."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock(spec=AsyncIOMotorDatabase)
        return db

    def test_command_listener_started(self):
        """Test command started event handling."""
        listener = PerformanceCommandListener()
        event = MagicMock()
        event.command_name = "find"
        event.request_id = 1
        event.database_name = "test_db"
        event.command = {"find": "test_collection"}

        listener.started(event)
        # No assertions needed as this just logs

    def test_command_listener_succeeded_slow_query(self):
        """Test slow query detection in command succeeded event."""
        listener = PerformanceCommandListener()
        event = MagicMock()
        event.command_name = "find"
        event.request_id = 1
        event.duration_micros = 1000000  # 1 second

        listener.succeeded(event)
        # No assertions needed as this just logs

    def test_command_listener_failed(self):
        """Test command failed event handling."""
        listener = PerformanceCommandListener()
        event = MagicMock()
        event.command_name = "find"
        event.failure = Exception("Test error")

        listener.failed(event)
        # No assertions needed as this just logs

    @pytest.mark.asyncio
    async def test_monitor_performance_decorator_success(self):
        """Test performance monitoring decorator success case."""

        @monitor_performance
        async def test_func():
            return "success"

        result = await test_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_monitor_performance_decorator_error(self):
        """Test performance monitoring decorator error case."""

        @monitor_performance
        async def test_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            await test_func()

    @pytest.mark.asyncio
    async def test_get_collection_stats(self, mock_db: AsyncIOMotorDatabase):
        """Test collection statistics retrieval."""
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_stats = {"size": 1000, "count": 100}
        mock_collection.stats = AsyncMock(return_value=mock_stats)

        stats = await get_collection_stats(mock_db, "test_collection")
        assert stats == mock_stats

    @pytest.mark.asyncio
    async def test_analyze_query_performance(self, mock_db: AsyncIOMotorDatabase):
        """Test query performance analysis."""
        # Mock collection
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection

        # Mock explain output
        mock_explain_output = {
            "executionStats": {
                "executionTimeMillis": 50,
                "totalDocsExamined": 100,
                "nReturned": 10,
            },
            "queryPlanner": {
                "winningPlan": {"inputStage": {"indexName": "test_index"}}
            },
        }

        # Create a mock cursor that supports explain
        mock_cursor = AsyncMock()
        mock_cursor.explain = AsyncMock(return_value=mock_explain_output)
        mock_collection.find = MagicMock(return_value=mock_cursor)

        result = await analyze_query_performance(
            mock_db, "test_collection", {"test": "query"}
        )

        assert result == mock_explain_output
        mock_cursor.explain.assert_called_once_with("executionStats")
