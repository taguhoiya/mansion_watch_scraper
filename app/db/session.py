"""MongoDB session management module."""

import logging
import os
from typing import Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.monitoring import register
from pymongo.server_api import ServerApi

from app.configs.settings import settings
from app.db.monitoring import PerformanceCommandListener

logger = logging.getLogger(__name__)

# Register performance monitoring listener
register(PerformanceCommandListener())


def get_client_options() -> Dict:
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
    if settings.ENV not in ["development", "docker"]:
        options.update(
            {
                "tls": True,
                "tlsAllowInvalidCertificates": False,  # Enforce certificate validation
                "tlsInsecure": False,  # Don't skip certificate validation
                "tlsCAFile": "isrgrootx1.pem",  # Let's Encrypt Root CA
                "retryReads": True,
                "w": "majority",  # Write concern
                "journal": True,  # Wait for journal commit
                "readPreference": "primaryPreferred",
            }
        )

    return options


# Global client instance
client: Optional[AsyncIOMotorClient] = None


def get_db() -> AsyncIOMotorClient:
    """Get MongoDB database instance.

    Returns:
        AsyncIOMotorClient instance.
    """
    global client
    if not client:
        uri = os.getenv("MONGODB_URI", settings.MONGO_URI)
        if not uri:
            raise ValueError("MONGODB_URI environment variable not set")

        try:
            options = get_client_options()
            client = AsyncIOMotorClient(uri, **options)
            return client[settings.MONGO_DATABASE]
        except Exception as e:
            logger.error("Failed to connect to MongoDB: %s", str(e))
            raise

    return client[settings.MONGO_DATABASE]


def get_client() -> AsyncIOMotorClient:
    """Get MongoDB client instance.

    Returns:
        AsyncIOMotorClient instance.
    """
    global client
    if not client:
        uri = os.getenv("MONGODB_URI", settings.MONGO_URI)
        if not uri:
            raise ValueError("MONGODB_URI environment variable not set")

        try:
            options = get_client_options()
            client = AsyncIOMotorClient(uri, **options)
        except Exception as e:
            logger.error("Failed to connect to MongoDB: %s", str(e))
            raise

    return client


async def init_db() -> None:
    """Initialize database connection."""
    db = get_client()
    try:
        # Verify database connection
        await db.admin.command("ping")
    except Exception as e:
        logger.error("Failed to connect to MongoDB: %s", str(e))
        raise
