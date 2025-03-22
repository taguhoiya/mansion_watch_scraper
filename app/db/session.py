"""MongoDB session management module."""

from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.monitoring import register
from pymongo.server_api import ServerApi

from app.configs.settings import settings
from app.db.monitoring import PerformanceCommandListener

# Register performance monitoring listener
register(PerformanceCommandListener())

# Global client instance
client: Optional[AsyncIOMotorClient] = None


def get_client_options() -> Dict[str, Any]:
    """Get MongoDB client options based on environment."""
    options = {
        "server_api": ServerApi("1"),
        "retryWrites": True,
        "maxPoolSize": settings.MONGO_MAX_POOL_SIZE,
        "minPoolSize": settings.MONGO_MIN_POOL_SIZE,
        "maxIdleTimeMS": settings.MONGO_MAX_IDLE_TIME_MS,
        "serverSelectionTimeoutMS": 30000,  # Increased timeout for server selection
        "connectTimeoutMS": settings.MONGO_CONNECT_TIMEOUT_MS,
        "waitQueueTimeoutMS": settings.MONGO_WAIT_QUEUE_TIMEOUT_MS,
        "heartbeatFrequencyMS": 10000,  # More frequent server checks
        "localThresholdMS": 15,  # Smaller threshold for selecting nearest server
    }

    # Enable TLS and other security settings for MongoDB Atlas or production environments
    if "mongodb+srv" in settings.MONGO_URI or settings.ENV not in [
        "development",
        "docker",
    ]:
        options.update(
            {
                "tls": True,  # Use TLS for connection
                "tlsInsecure": False,  # Enforce strict TLS verification
                "retryReads": True,
                "w": "majority",
                "journal": True,
            }
        )

    return options


def get_client() -> AsyncIOMotorClient:
    """Get MongoDB client instance."""
    global client
    if client is None:
        client = AsyncIOMotorClient(settings.MONGO_URI, **get_client_options())
    return client


def get_db(database_name: str = None) -> AsyncIOMotorDatabase:
    """Get MongoDB database instance.

    Args:
        database_name: The name of the database to connect to.
            If None, uses the default database from settings.

    Returns:
        AsyncIOMotorDatabase: The database instance.
    """
    if database_name is None:
        database_name = settings.MONGO_DATABASE
    return get_client()[database_name]


async def init_db() -> None:
    """Initialize database connection."""
    db = get_db()
    try:
        # Verify database connection
        await db.command("ping")
    except Exception as e:
        raise Exception(f"Failed to connect to MongoDB: {e}")
