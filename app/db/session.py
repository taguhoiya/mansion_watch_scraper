"""MongoDB session management module."""

import logging
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.monitoring import register
from pymongo.server_api import ServerApi

from app.configs.settings import settings
from app.db.monitoring import PerformanceCommandListener

logger = logging.getLogger(__name__)

# Register performance monitoring listener
register(PerformanceCommandListener())

# Global client instance
client: Optional[AsyncIOMotorClient] = None


def get_client_options() -> Dict[str, Any]:
    """Get MongoDB client options based on environment.

    Returns:
        Dict of client options.
    """
    options = {
        "server_api": ServerApi("1"),
        "retryWrites": True,
        "maxPoolSize": settings.MONGO_MAX_POOL_SIZE,
        "minPoolSize": settings.MONGO_MIN_POOL_SIZE,
        "maxIdleTimeMS": settings.MONGO_MAX_IDLE_TIME_MS,
        "serverSelectionTimeoutMS": 30000,
        "connectTimeoutMS": settings.MONGO_CONNECT_TIMEOUT_MS,
        "waitQueueTimeoutMS": settings.MONGO_WAIT_QUEUE_TIMEOUT_MS,
        "heartbeatFrequencyMS": 10000,
        "localThresholdMS": 15,
        "appName": "mansion_watch",  # Help identify the application in MongoDB logs
    }

    # Enable TLS and other security settings for MongoDB Atlas or production environments
    if "mongodb+srv" in settings.MONGO_URI or settings.ENV not in [
        "development",
        "docker",
    ]:
        options.update(
            {
                "tls": True,
                "tlsCAFile": "isrgrootx1.pem",  # Let's Encrypt Root CA
                "tlsMinVersion": "TLSv1.2",  # Ensure minimum TLS 1.2 for Atlas compatibility
                "retryReads": True,
                "w": "majority",
                "journal": True,
                "readPreference": "primaryPreferred",
            }
        )

    return options


def get_client() -> AsyncIOMotorClient:
    """Get MongoDB client instance.

    Returns:
        AsyncIOMotorClient instance.
    """
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
        logger.error("Failed to connect to MongoDB: %s", str(e))
        raise
