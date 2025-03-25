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

from app.configs.settings import settings


@pytest.fixture(scope="session")
def anyio_backend():
    """Return the backend to use for anyio."""
    return "asyncio"


@pytest.fixture(scope="function")
async def event_loop():
    """Create an instance of the default event loop for each test case."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)


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
def mock_motor_client(event_loop):
    """Create a mock AsyncIOMotorClient with comprehensive mocking."""
    mock_client = MagicMock(spec=AsyncIOMotorClient)
    mock_db = MagicMock(spec=AsyncIOMotorDatabase)
    mock_collections = {
        settings.COLLECTION_USERS: AsyncMock(
            spec=AsyncIOMotorCollection,
            count_documents=AsyncMock(return_value=0),
        ),
        settings.COLLECTION_PROPERTIES: AsyncMock(
            spec=AsyncIOMotorCollection,
            count_documents=AsyncMock(return_value=0),
        ),
        settings.COLLECTION_USER_PROPERTIES: AsyncMock(
            spec=AsyncIOMotorCollection,
            count_documents=AsyncMock(return_value=0),
        ),
    }
    mock_db.__getitem__.side_effect = mock_collections.__getitem__
    mock_client.__getitem__.return_value = mock_db
    mock_client.admin.command = AsyncMock(return_value={"ok": 1})

    with patch("motor.motor_asyncio.AsyncIOMotorClient", return_value=mock_client):
        yield mock_client, mock_collections


@pytest.fixture
def mock_db() -> Generator[MagicMock, None, None]:
    """
    Mock MongoDB database for testing database operations.

    This fixture creates a mock database instance that returns mock collections
    when accessed with the dictionary syntax (db[collection_name]).

    Returns:
        MagicMock: A mock of the AsyncIOMotorDatabase
    """
    mock_db_instance = MagicMock(spec=AsyncIOMotorDatabase)

    # Create mock collections
    mock_properties = AsyncMock()
    mock_user_properties = AsyncMock()
    mock_users = AsyncMock(count_documents=AsyncMock(return_value=0))
    mock_properties_collection = AsyncMock(count_documents=AsyncMock(return_value=0))
    mock_user_properties_collection = AsyncMock(
        count_documents=AsyncMock(return_value=0)
    )

    # Set up collection mapping
    collections = {
        "properties": mock_properties,
        "user_properties": mock_user_properties,
        settings.COLLECTION_USERS: mock_users,
        settings.COLLECTION_PROPERTIES: mock_properties_collection,
        settings.COLLECTION_USER_PROPERTIES: mock_user_properties_collection,
    }

    # Set up the __getitem__ method to return appropriate mock collections
    mock_db_instance.__getitem__.side_effect = lambda x: collections.get(x, AsyncMock())

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


@pytest.fixture(autouse=True)
def mock_google_auth():
    """Mock Google Cloud authentication for all tests."""
    with patch("google.auth.default") as mock:
        mock.return_value = (MagicMock(), "mock-project")
        yield mock


@pytest.fixture(autouse=True)
def mock_google_cloud_storage():
    """Mock Google Cloud Storage for all tests."""
    with patch("google.cloud.storage.Client") as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client
        yield mock_client


@pytest.fixture(autouse=True)
def mock_gcp_credentials():
    """Mock Google Cloud credentials for all tests."""
    with patch.dict(
        os.environ,
        {
            "GOOGLE_APPLICATION_CREDENTIALS": "dummy-credentials.json",
            "GCP_PROJECT_ID": "dummy-project",
            "PUBSUB_TOPIC": "dummy-topic",
        },
    ):
        yield


@pytest.fixture(autouse=True)
def mock_pubsub_client():
    """Mock Google Cloud Pub/Sub client for all tests."""
    with patch("google.cloud.pubsub_v1.PublisherClient") as mock_publisher:
        # Create a mock future for publish calls
        mock_future = MagicMock()
        mock_future.result.return_value = "test_message_id"
        mock_publisher.return_value.publish.return_value = mock_future
        mock_publisher.return_value.topic_path.return_value = "test_topic_path"

        # Create a mock subscriber
        with patch("google.cloud.pubsub_v1.SubscriberClient") as mock_subscriber:
            mock_subscriber.return_value.subscription_path.return_value = (
                "test_subscription_path"
            )
            yield mock_publisher, mock_subscriber
