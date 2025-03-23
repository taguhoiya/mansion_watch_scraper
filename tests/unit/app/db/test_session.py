"""Test MongoDB session management."""

from unittest.mock import AsyncMock, patch

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from pymongo.server_api import ServerApi

from app.db.session import get_client, get_client_options, get_db, init_db


@pytest.fixture
def mock_env_development():
    """Mock development environment."""
    with patch.dict("os.environ", {"ENV": "development"}):
        yield


@pytest.fixture
def mock_env_production():
    """Mock production environment."""
    with patch.dict("os.environ", {"ENV": "production"}):
        yield


def test_get_client_options_development(mock_env_development):
    """Test client options in development environment."""
    options = get_client_options()

    assert isinstance(options["server_api"], ServerApi)
    assert options["server_api"].version == "1"
    assert options["retryWrites"] is True
    assert options["maxPoolSize"] == 100
    assert options["minPoolSize"] == 3
    assert options["maxIdleTimeMS"] == 30000
    assert options["serverSelectionTimeoutMS"] == 30000
    assert options["socketTimeoutMS"] == 30000
    assert options["connectTimeoutMS"] == 30000
    assert options["waitQueueTimeoutMS"] == 10000
    assert options["heartbeatFrequencyMS"] == 10000
    assert options["retryReads"] is True
    assert options["w"] == "majority"
    assert options["readPreference"] == "primaryPreferred"


def test_get_client_options_production(mock_env_production):
    """Test client options in production environment."""
    with patch("app.configs.settings.settings.ENV", "production"):
        options = get_client_options()

        assert isinstance(options["server_api"], ServerApi)
        assert options["server_api"].version == "1"
        assert options["retryWrites"] is True
        assert options["maxPoolSize"] == 100
        assert options["minPoolSize"] == 3
        assert options["maxIdleTimeMS"] == 30000
        assert options["serverSelectionTimeoutMS"] == 30000
        assert options["socketTimeoutMS"] == 30000
        assert options["connectTimeoutMS"] == 30000
        assert options["waitQueueTimeoutMS"] == 10000
        assert options["heartbeatFrequencyMS"] == 10000
        assert options["retryReads"] is True
        assert options["w"] == "majority"
        assert options["readPreference"] == "primaryPreferred"


@pytest.fixture
def mock_mongo_client():
    """Create a mock MongoDB client."""
    mock_client = AsyncMock(spec=AsyncIOMotorClient)
    mock_admin = AsyncMock()
    mock_client.admin = mock_admin
    mock_admin.command = AsyncMock()
    return mock_client


@pytest.fixture(autouse=True)
def reset_client():
    """Reset the MongoDB client before each test."""
    from app.db import session

    session._client = None
    yield
    session._client = None


@pytest.mark.asyncio
async def test_init_db_success(mock_mongo_client):
    """Test successful database initialization."""
    with patch("app.db.session.AsyncIOMotorClient", return_value=mock_mongo_client):
        await init_db()
        client = get_client()
        assert client is mock_mongo_client
        mock_mongo_client.admin.command.assert_called_once_with("ping")


@pytest.mark.asyncio
async def test_init_db_retry(mock_mongo_client):
    """Test database initialization with retry."""
    mock_mongo_client.admin.command = AsyncMock(
        side_effect=[ConnectionFailure("Test error"), None]
    )

    with patch("app.db.session.AsyncIOMotorClient", return_value=mock_mongo_client):
        await init_db()
        client = get_client()
        assert client is mock_mongo_client
        assert mock_mongo_client.admin.command.call_count == 2


@pytest.mark.asyncio
async def test_init_db_failure(mock_mongo_client):
    """Test database initialization failure."""
    mock_mongo_client.admin.command = AsyncMock(
        side_effect=ConnectionFailure("Test error")
    )

    with patch("app.db.session.AsyncIOMotorClient", return_value=mock_mongo_client):
        with pytest.raises(ConnectionFailure):
            await init_db()


def test_get_client_not_initialized():
    """Test getting client before initialization."""
    with pytest.raises(RuntimeError) as exc_info:
        get_client()
    assert (
        str(exc_info.value) == "MongoDB client not initialized. Call init_db() first."
    )


def test_get_db_not_initialized():
    """Test getting database before initialization."""
    with pytest.raises(RuntimeError) as exc_info:
        get_db()
    assert (
        str(exc_info.value) == "MongoDB client not initialized. Call init_db() first."
    )


@pytest.mark.asyncio
async def test_client_singleton(mock_mongo_client):
    """Test that the MongoDB client is a singleton."""
    with patch("app.db.session.AsyncIOMotorClient", return_value=mock_mongo_client):
        await init_db()
        client1 = get_client()
        client2 = get_client()

        assert client1 is client2
        assert mock_mongo_client.admin.command.call_count == 1
