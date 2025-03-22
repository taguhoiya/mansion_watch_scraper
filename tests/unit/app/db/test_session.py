import os
from unittest.mock import MagicMock, patch

import certifi
import pytest
from pymongo.server_api import ServerApi

from app.db.session import get_client_options, get_db


@pytest.fixture
def mock_env_development():
    """Mock environment variables for development."""
    with patch.dict(
        os.environ,
        {
            "ENV": "development",
            "MONGO_URI": "mongodb://localhost:27017",
            "MONGO_DATABASE": "test_db",
        },
    ):
        yield


@pytest.fixture
def mock_env_docker():
    """Mock environment variables for docker environment."""
    with patch.dict(
        os.environ,
        {
            "ENV": "docker",
            "MONGO_URI": "mongodb://mongodb:27017",
            "MONGO_DATABASE": "test_db",
        },
    ):
        yield


@pytest.fixture
def mock_env_production():
    """Mock environment variables for production."""
    with patch.dict(
        os.environ,
        {
            "ENV": "production",
            "MONGO_URI": "mongodb+srv://user:pass@cluster.mongodb.net/",
            "MONGO_DATABASE": "test_db",
        },
    ):
        yield


def test_get_client_options_development(mock_env_development):
    """Test client options in development environment."""
    options = get_client_options()

    assert isinstance(options["server_api"], ServerApi)
    assert options["server_api"].version == "1"
    assert "tls" not in options
    assert "tlsCAFile" not in options


def test_get_client_options_docker(mock_env_docker):
    """Test client options in docker environment."""
    options = get_client_options()

    assert isinstance(options["server_api"], ServerApi)
    assert options["server_api"].version == "1"
    assert "tls" not in options
    assert "tlsCAFile" not in options


def test_get_client_options_production(mock_env_production):
    """Test client options in production environment."""
    options = get_client_options()

    assert isinstance(options["server_api"], ServerApi)
    assert options["server_api"].version == "1"
    assert options["tls"] is True
    assert options["tlsCAFile"] == certifi.where()
    assert options["retryWrites"] is True
    assert options["w"] == "majority"
    assert options["appName"] == "MansionWatch"


@pytest.mark.asyncio
async def test_get_db_development(mock_env_development):
    """Test database connection in development environment."""
    with patch("app.db.session.client") as mock_client:
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        db = get_db()

        assert db == mock_db
        mock_client.__getitem__.assert_called_once_with("test_db")


@pytest.mark.asyncio
async def test_get_db_production(mock_env_production):
    """Test database connection in production environment."""
    with patch("app.db.session.client") as mock_client:
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        db = get_db()

        assert db == mock_db
        mock_client.__getitem__.assert_called_once_with("test_db")


@pytest.mark.asyncio
async def test_get_db_missing_database():
    """Test error when MONGO_DATABASE is not set."""
    with patch.dict(os.environ, {"MONGO_DATABASE": ""}):
        with pytest.raises(
            ValueError, match="MONGO_DATABASE environment variable is not set"
        ):
            get_db()


@pytest.mark.asyncio
async def test_get_db_connection_error():
    """Test database connection error handling."""
    with patch("app.db.session.client") as mock_client:
        mock_client.__getitem__.side_effect = Exception("Connection failed")

        with pytest.raises(Exception, match="Connection failed"):
            get_db()
