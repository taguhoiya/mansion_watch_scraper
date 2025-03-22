"""Test module for MongoDB index management."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from pymongo.server_api import ServerApi

from app.configs.settings import settings
from app.db.session import get_client_options

# We need to patch the client before importing get_db to properly test it
with patch("motor.motor_asyncio.AsyncIOMotorClient"):
    from app.db.session import get_db


@pytest.fixture(autouse=True)
def clean_env():
    """Fixture to ensure clean environment variables for each test."""
    original_env = dict(os.environ)
    os.environ.clear()
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_env_development(clean_env):
    """Fixture to mock development environment variables."""
    env_vars = {
        "ENV": "development",
        "MONGO_DATABASE": "test_db",
        "MONGO_URI": "mongodb://localhost:27017",
    }
    with patch.dict(os.environ, env_vars):
        yield


@pytest.fixture
def mock_env_production():
    """Mock production environment."""
    with patch("app.configs.settings.settings.ENV", "production"):
        yield


def test_get_client_options_development(mock_env_development):
    """Test client options in development environment."""
    options = get_client_options()

    # Check base options that should be present in all environments
    assert isinstance(options["server_api"], ServerApi)
    assert isinstance(options["server_api"].version, str)
    assert (
        options.get("serverSelectionTimeoutMS", 0) >= 0
    )  # Should be a non-negative number if present
    assert (
        options.get("connectTimeoutMS", 0) >= 0
    )  # Should be a non-negative number if present
    assert options.get("maxPoolSize", 1) >= 1  # Should be at least 1 if present
    assert options.get("minPoolSize", 0) >= 0  # Should be non-negative if present
    assert options.get("maxIdleTimeMS", 0) >= 0  # Should be non-negative if present
    assert options.get("retryWrites", False) in [
        True,
        False,
    ]  # Should be boolean if present

    # Check that production-only options are not present
    assert "tls" not in options
    assert "tlsCAFile" not in options
    assert "w" not in options


def test_get_client_options_production(mock_env_production):
    """Test client options in production environment."""
    with patch("app.configs.settings.settings.ENV", "production"):
        options = get_client_options()
        assert options["tls"] is True
        assert options["retryReads"] is True
        assert options["w"] == "majority"
        assert options["journal"] is True


async def test_get_db_success(mock_env_development):
    """Test successful database connection."""
    with patch("app.db.session.client") as mock_client:
        # Setup mock client
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        # Test get_db uses the configured database name
        db = get_db()
        assert db == mock_db
        mock_client.__getitem__.assert_called_once_with(settings.MONGO_DATABASE)


@pytest.mark.asyncio
async def test_get_db_connection_error(mock_env_development):
    """Test database connection error handling."""
    with patch("app.db.session.client") as mock_client:
        # Setup mock client to raise an error
        mock_client.__getitem__.side_effect = Exception("Connection failed")

        # Test that the error is propagated
        with pytest.raises(Exception) as exc_info:
            get_db()
        assert str(exc_info.value) == "Connection failed"


def test_client_singleton():
    """Test that the MongoDB client is a singleton."""
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as mock_client:
        # Reset the module to force client recreation
        with patch.dict("sys.modules"):
            if "app.db.session" in sys.modules:
                del sys.modules["app.db.session"]

            # Import the module twice to test singleton behavior
            from app.db.session import get_client

            # Get client twice
            client1 = get_client()
            client2 = get_client()

            # Both calls should reference the same client instance
            assert client1 is client2

            # Client should only be created once
            mock_client.assert_called_once()
            args, kwargs = mock_client.call_args
            assert args[0] == settings.MONGO_URI
            assert isinstance(kwargs["server_api"], ServerApi)
            assert kwargs["server_api"].version == "1"
            assert kwargs["retryWrites"] is True
            assert kwargs["maxPoolSize"] == settings.MONGO_MAX_POOL_SIZE
            assert kwargs["minPoolSize"] == settings.MONGO_MIN_POOL_SIZE
            assert kwargs["maxIdleTimeMS"] == settings.MONGO_MAX_IDLE_TIME_MS
            assert kwargs["serverSelectionTimeoutMS"] == 30000
            assert kwargs["connectTimeoutMS"] == settings.MONGO_CONNECT_TIMEOUT_MS
            assert kwargs["waitQueueTimeoutMS"] == settings.MONGO_WAIT_QUEUE_TIMEOUT_MS
            assert kwargs["heartbeatFrequencyMS"] == 10000
            assert kwargs["localThresholdMS"] == 15
