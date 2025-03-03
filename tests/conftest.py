import asyncio
import os
import warnings
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """
    Return an event loop policy with a new event loop for each test.

    This fixture ensures proper isolation between tests by providing
    a fresh event loop for each test function.

    Returns:
        asyncio.AbstractEventLoopPolicy: The current event loop policy
    """
    return asyncio.get_event_loop_policy()


@pytest.fixture(autouse=True)
def suppress_await_warnings() -> Generator[None, None, None]:
    """
    Suppress warnings about unawaited coroutines from AsyncMock.

    This fixture temporarily modifies the warning filters to ignore
    RuntimeWarnings about coroutines not being awaited, which are common
    when using AsyncMock in tests. The original filters are restored after
    the test completes.

    Yields:
        None
    """
    # Save original warning filters
    original_filters = warnings.filters.copy()

    # Filter out RuntimeWarning about coroutines not being awaited
    warnings.filterwarnings(
        "ignore", message="coroutine '.*' was never awaited", category=RuntimeWarning
    )

    yield

    # Restore original warning filters
    warnings.filters = original_filters


@pytest.fixture
def mock_mongo_client() -> Generator[MagicMock, None, None]:
    """
    Mock MongoDB client for testing database interactions.

    This fixture patches the AsyncIOMotorClient to avoid actual database
    connections during tests.

    Yields:
        MagicMock: A mock of the AsyncIOMotorClient
    """
    with patch("app.db.session.AsyncIOMotorClient") as mock_client:
        mock_instance = MagicMock(spec=AsyncIOMotorClient)
        mock_client.return_value = mock_instance
        yield mock_client


@pytest.fixture
def mock_db() -> Generator[MagicMock, None, None]:
    """
    Mock MongoDB database for testing database operations.

    This fixture creates a mock database instance that returns mock collections
    when accessed with the dictionary syntax (db[collection_name]).

    Yields:
        MagicMock: A mock of the AsyncIOMotorDatabase
    """
    mock_db_instance = MagicMock(spec=AsyncIOMotorDatabase)

    # Create a function to return mock collections
    def get_collection(collection_name: str) -> AsyncMock:
        """Return a mock collection for the given name."""
        return AsyncMock(spec=AsyncIOMotorCollection)

    # Set up the __getitem__ method to return a mock collection
    mock_db_instance.__getitem__.side_effect = get_collection

    with patch("app.db.session.get_db", return_value=mock_db_instance):
        yield mock_db_instance


@pytest.fixture
def mock_env_vars() -> Generator[None, None, None]:
    """
    Set up environment variables for testing.

    This fixture temporarily sets environment variables needed for tests,
    and restores the original environment after the test completes.

    Yields:
        None
    """
    original_env = os.environ.copy()

    # Set test environment variables
    test_env_vars = {
        "LINE_CHANNEL_SECRET": "test_channel_secret",
        "LINE_CHANNEL_ACCESS_TOKEN": "test_access_token",
        "MONGO_URI": "mongodb://localhost:27017",
        "MONGO_DATABASE": "test_db",
        "COLLECTION_USERS": "test_users",
    }

    os.environ.update(test_env_vars)

    yield

    # Restore original environment variables
    os.environ.clear()
    os.environ.update(original_env)
