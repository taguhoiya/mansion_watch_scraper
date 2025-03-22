import os
import sys
from unittest.mock import MagicMock, patch

import certifi
import pytest
from pymongo.server_api import ServerApi

from app.db.session import get_client_options

# We need to patch the client before importing get_db to properly test it
with patch("motor.motor_asyncio.AsyncIOMotorClient"):
    from app.db.session import get_db


@pytest.fixture
def mock_env_development():
    """Fixture to mock development environment variables."""
    with patch.dict(os.environ, {"ENV": "development", "MONGO_DATABASE": "test_db"}):
        yield


@pytest.fixture
def mock_env_production():
    """Fixture to mock production environment variables."""
    with patch.dict(os.environ, {"ENV": "production", "MONGO_DATABASE": "test_db"}):
        yield


def test_get_client_options_development(mock_env_development):
    """Test client options in development environment."""
    options = get_client_options()

    # Check base options that should be present in all environments
    assert isinstance(options["server_api"], ServerApi)
    assert options["serverSelectionTimeoutMS"] == 5000
    assert options["connectTimeoutMS"] == 10000
    assert options["maxPoolSize"] == 100
    assert options["minPoolSize"] == 0
    assert options["maxIdleTimeMS"] == 30000
    assert options["retryWrites"] is True

    # Check that production-only options are not present
    assert "tls" not in options
    assert "tlsCAFile" not in options
    assert "w" not in options
    assert "journal" not in options


def test_get_client_options_production(mock_env_production):
    """Test client options in production environment."""
    options = get_client_options()

    # Check all production options
    assert options["tls"] is True
    assert options["tlsCAFile"] == certifi.where()
    assert options["w"] == "majority"
    assert options["journal"] is True
    assert options["appName"] == "MansionWatch"

    # Check base options are still present
    assert isinstance(options["server_api"], ServerApi)
    assert options["serverSelectionTimeoutMS"] == 5000


@pytest.mark.asyncio
async def test_get_db_success(mock_env_development):
    """Test successful database connection."""
    with patch("app.db.session.client") as mock_client:
        # Setup mock client
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        # Test get_db
        db = get_db()
        assert db == mock_db
        mock_client.__getitem__.assert_called_once_with("test_db")


@pytest.mark.asyncio
async def test_get_db_missing_database():
    """Test database connection with missing database name."""
    with patch.dict(os.environ, {"MONGO_DATABASE": ""}):
        with pytest.raises(ValueError) as exc_info:
            get_db()
        assert str(exc_info.value) == "MONGO_DATABASE environment variable is not set"


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
            from app.db.session import client as client1
            from app.db.session import client as client2

            # Both imports should reference the same client instance
            assert client1 is client2

            # Client should only be created once
            mock_client.assert_called_once()
