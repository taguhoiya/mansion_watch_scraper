import os
from typing import AsyncGenerator, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)
from pymongo.errors import (
    ConnectionFailure,
    OperationFailure,
    ServerSelectionTimeoutError,
)
from pymongo.results import InsertOneResult

from app.configs.settings import Settings
from seed import seed_database

# Get collection names from settings
settings = Settings()
COLLECTION_USERS = settings.COLLECTION_USERS
COLLECTION_PROPERTIES = settings.COLLECTION_PROPERTIES
COLLECTION_USER_PROPERTIES = settings.COLLECTION_USER_PROPERTIES


@pytest.fixture
def mock_env_vars_seed() -> Dict[str, str]:
    """Set up environment variables for seed testing with proper typing."""
    original_env = os.environ.copy()
    test_env_vars = {
        "MONGO_URI": "mongodb://localhost:27017",
        "MONGO_DATABASE": "test_db",
        "COLLECTION_USERS": "users",
        "COLLECTION_PROPERTIES": "properties",
        "COLLECTION_USER_PROPERTIES": "user_properties",
        "ENV": "development",
    }
    with patch.dict(os.environ, test_env_vars, clear=True):
        yield test_env_vars
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_motor_client(
    event_loop,
) -> tuple[MagicMock, Dict[str, AsyncMock]]:
    """Mock MongoDB motor client with proper typing and comprehensive mocking."""
    mock_instance = MagicMock(spec=AsyncIOMotorClient)
    mock_db = MagicMock(spec=AsyncIOMotorDatabase)
    mock_collections = {
        COLLECTION_USERS: AsyncMock(spec=AsyncIOMotorCollection),
        COLLECTION_PROPERTIES: AsyncMock(spec=AsyncIOMotorCollection),
        COLLECTION_USER_PROPERTIES: AsyncMock(spec=AsyncIOMotorCollection),
    }

    # Set up async methods with proper coroutine returns
    for collection in mock_collections.values():
        collection.count_documents = AsyncMock(return_value=0)
        collection.insert_one = AsyncMock()

    mock_db.__getitem__.side_effect = mock_collections.__getitem__
    mock_instance.__getitem__.return_value = mock_db

    # Mock the admin command for ping
    mock_admin = AsyncMock(spec=AsyncIOMotorCollection)
    mock_admin.command = AsyncMock(return_value={"ok": 1})
    mock_instance.admin = mock_admin

    with (
        patch("motor.motor_asyncio.AsyncIOMotorClient", return_value=mock_instance),
        patch("app.db.session._client", mock_instance),
        patch("app.db.session.get_client", return_value=mock_instance),
        patch("app.db.session.init_db"),
    ):
        yield mock_instance, mock_collections


@pytest.mark.asyncio
async def test_seed_database_production_environment(
    mock_env_vars_seed: Dict[str, str],
) -> None:
    """Test that seeding is not allowed in production environment."""
    with (
        patch.dict(os.environ, {"ENV": "production"}, clear=True),
        patch("seed.os.getenv", return_value="production"),
        patch("seed.ENV", "production"),
        patch("motor.motor_asyncio.AsyncIOMotorClient") as mock_client,
    ):
        with pytest.raises(SystemExit) as exc_info:
            await seed_database()
        assert exc_info.value.code == 1
        # Verify that we never tried to create a MongoDB client
        mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_seed_database_development_environment(
    mock_env_vars_seed: Dict[str, str],
    mock_motor_client: tuple[MagicMock, Dict[str, AsyncMock]],
) -> None:
    """Test that seeding is allowed in development environment."""
    mock_client, mock_collections = mock_motor_client

    # Configure mock collections
    for collection in mock_collections.values():
        collection.count_documents = AsyncMock(return_value=0)
        collection.insert_one = AsyncMock(
            return_value=InsertOneResult(ObjectId(), True)
        )

    with patch.dict(os.environ, {"ENV": "development"}, clear=True):
        with (
            patch("seed.os.getenv", return_value="development"),
            patch("app.db.session.get_client", return_value=mock_client),
            patch("app.db.session.init_db", return_value=None),
        ):
            await seed_database()

    # Verify client configuration
    mock_client.admin.command.assert_called_once_with("ping")


@pytest.mark.asyncio
async def test_seed_database_test_environment(
    mock_env_vars_seed: Dict[str, str],
    mock_motor_client: tuple[MagicMock, Dict[str, AsyncMock]],
) -> None:
    """Test that seeding is allowed in test environment."""
    mock_client, mock_collections = mock_motor_client

    # Configure mock collections
    for collection in mock_collections.values():
        collection.count_documents = AsyncMock(return_value=0)
        collection.insert_one = AsyncMock(
            return_value=InsertOneResult(ObjectId(), True)
        )

    with patch.dict(os.environ, {"ENV": "test"}, clear=True):
        with patch("seed.os.getenv") as mock_getenv:
            mock_getenv.return_value = "test"
            await seed_database()


@pytest.mark.asyncio
async def test_seed_database_empty_collections(
    mock_env_vars_seed: Dict[str, str],
    mock_motor_client: tuple[MagicMock, Dict[str, AsyncMock]],
) -> None:
    """Test seeding database when collections are empty with comprehensive validation."""
    mock_client, mock_collections = mock_motor_client

    # Configure mock collections
    for collection in mock_collections.values():
        collection.count_documents = AsyncMock(return_value=0)
        collection.insert_one = AsyncMock(
            return_value=InsertOneResult(ObjectId(), True)
        )

    with (
        patch("app.db.session.get_client", return_value=mock_client),
        patch("app.db.session.init_db", return_value=None),
    ):
        await seed_database()

    # Verify client configuration
    mock_client.admin.command.assert_called_once_with("ping")


@pytest.fixture
async def mock_mongo_client_seed() -> (
    AsyncGenerator[tuple[MagicMock, Dict[str, AsyncMock]], None]
):
    """Create a mock MongoDB client for seed tests."""
    # Create mock collections
    mock_users = AsyncMock(spec=AsyncIOMotorCollection)
    mock_users.count_documents = AsyncMock(return_value=1)

    mock_properties = AsyncMock(spec=AsyncIOMotorCollection)
    mock_properties.count_documents = AsyncMock(return_value=1)

    mock_user_properties = AsyncMock(spec=AsyncIOMotorCollection)
    mock_user_properties.count_documents = AsyncMock(return_value=1)

    # Create mock database
    mock_db = MagicMock(spec=AsyncIOMotorDatabase)
    mock_collections = {
        COLLECTION_USERS: mock_users,
        COLLECTION_PROPERTIES: mock_properties,
        COLLECTION_USER_PROPERTIES: mock_user_properties,
    }
    mock_db.__getitem__.side_effect = mock_collections.__getitem__

    # Set up client mock
    mock_client = MagicMock(spec=AsyncIOMotorClient)
    mock_client.__getitem__.return_value = mock_db

    # Set up environment variables and module-level constants
    env_vars = {
        "ENV": "development",
        "MONGO_URI": "mongodb://localhost:27017",
        "DB_NAME": "test_db",
        "COLLECTION_USERS": "users",
        "COLLECTION_PROPERTIES": "properties",
        "COLLECTION_USER_PROPERTIES": "user_properties",
    }

    with (
        patch.dict(os.environ, env_vars, clear=True),
        patch("seed.os.getenv", side_effect=env_vars.get),
        patch("motor.motor_asyncio.AsyncIOMotorClient", return_value=mock_client),
        patch("seed.MONGO_URI", env_vars["MONGO_URI"]),
        patch("seed.DB_NAME", env_vars["DB_NAME"]),
        patch("seed.COLLECTION_USERS", env_vars["COLLECTION_USERS"]),
        patch("seed.COLLECTION_PROPERTIES", env_vars["COLLECTION_PROPERTIES"]),
        patch(
            "seed.COLLECTION_USER_PROPERTIES", env_vars["COLLECTION_USER_PROPERTIES"]
        ),
        patch("seed.ENV", env_vars["ENV"]),
    ):
        yield mock_client, mock_collections


@pytest.fixture
async def mock_env_seed() -> AsyncGenerator[None, None]:
    """Set up environment variables for seed tests."""
    with patch.dict(os.environ, {"ENV": "development"}, clear=True):
        with patch("seed.os.getenv") as mock_getenv:

            def getenv_side_effect(key, default=None):
                if key == "ENV":
                    return "development"
                return os.environ.get(key, default)

            mock_getenv.side_effect = getenv_side_effect

            with patch("seed.ENV", "development"):
                yield


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception_class,error_message",
    [
        (ConnectionFailure, "Failed to connect to MongoDB"),
        (ServerSelectionTimeoutError, "Server selection timeout"),
        (OperationFailure, "Authentication failed"),
        (Exception, "Unexpected error occurred"),
    ],
)
async def test_seed_database_connection_errors(
    mock_env_vars_seed: Dict[str, str],
    exception_class: type[Exception],
    error_message: str,
) -> None:
    """Test various database connection error scenarios."""
    mock_instance = MagicMock(spec=AsyncIOMotorClient)
    mock_admin_db = MagicMock()
    mock_admin_db.command = AsyncMock(side_effect=exception_class(error_message))
    mock_instance.admin = mock_admin_db

    with (
        patch("app.db.session.get_client", return_value=mock_instance),
        patch("app.db.session._client", mock_instance),
        patch("app.db.session.init_db", side_effect=exception_class(error_message)),
    ):
        with pytest.raises(exception_class, match=error_message):
            await seed_database()


@pytest.mark.asyncio
async def test_seed_database_invalid_uri(mock_env_vars_seed: Dict[str, str]) -> None:
    """Test handling of invalid MongoDB URI."""
    invalid_uri = "invalid://mongodb/uri"

    mock_instance = MagicMock(spec=AsyncIOMotorClient)
    mock_admin_db = MagicMock()
    mock_admin_db.command = AsyncMock(side_effect=Exception("Invalid URI"))
    mock_instance.admin = mock_admin_db

    with patch.dict(os.environ, {"MONGO_URI": invalid_uri}, clear=True):
        with (
            patch("seed.MONGO_URI", invalid_uri),
            patch("app.db.session.get_client", return_value=mock_instance),
            patch("app.db.session._client", mock_instance),
            patch("app.db.session.init_db", side_effect=Exception("Invalid URI")),
        ):
            with pytest.raises(Exception, match="Invalid URI"):
                await seed_database()
