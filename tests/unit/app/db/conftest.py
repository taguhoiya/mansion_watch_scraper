"""Common test fixtures for database tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase


@pytest.fixture
def mock_db() -> AsyncIOMotorDatabase:
    """Create a mock MongoDB database for testing.

    Returns:
        A mock AsyncIOMotorDatabase instance.
    """
    mock_db = MagicMock(spec=AsyncIOMotorDatabase)

    # Mock collections
    mock_properties = AsyncMock()
    mock_user_properties = AsyncMock()

    # Setup __getitem__ to return appropriate collection mocks
    mock_db.__getitem__.side_effect = lambda x: {
        "properties": mock_properties,
        "user_properties": mock_user_properties,
    }.get(x, AsyncMock())

    return mock_db
