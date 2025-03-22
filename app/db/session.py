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

    if settings.ENV not in ["development", "docker"]:
        options.update(
            {
                "tls": True,
                "tlsAllowInvalidCertificates": False,
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


def get_db() -> AsyncIOMotorDatabase:
    """Get MongoDB database instance.

    Returns:
        AsyncIOMotorDatabase: The database instance.
    """
    return get_client()[settings.MONGO_DATABASE]


async def init_db() -> None:
    """Initialize database connection."""
    db = get_db()
    try:
        # Verify database connection
        await db.command("ping")
    except Exception as e:
        raise Exception(f"Failed to connect to MongoDB: {e}")
