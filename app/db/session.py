"""MongoDB session management module."""

import asyncio
import logging
from typing import Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from pymongo.monitoring import register
from pymongo.server_api import ServerApi

from app.configs.settings import settings
from app.db.monitoring import PerformanceCommandListener

logger = logging.getLogger(__name__)

# Register performance monitoring
register(PerformanceCommandListener())

# Global client instance
_client: Optional[AsyncIOMotorClient] = None


def get_client_options() -> Dict:
    """Get MongoDB client options based on environment.

    Returns:
        Dict of MongoDB client options.
    """
    options = {
        "server_api": ServerApi("1"),
        "retryWrites": True,
        "maxPoolSize": settings.MONGO_MAX_POOL_SIZE,
        "minPoolSize": settings.MONGO_MIN_POOL_SIZE,
        "maxIdleTimeMS": settings.MONGO_MAX_IDLE_TIME_MS,
        "serverSelectionTimeoutMS": 60000,  # 60 seconds
        "socketTimeoutMS": 60000,  # 60 seconds
        "connectTimeoutMS": settings.MONGO_CONNECT_TIMEOUT_MS,
        "waitQueueTimeoutMS": settings.MONGO_WAIT_QUEUE_TIMEOUT_MS,
        "heartbeatFrequencyMS": 10000,  # 10 seconds
        "retryReads": True,
        "w": "majority",  # Write concern
        "readPreference": "primaryPreferred",  # Read preference
    }

    # Add TLS options for MongoDB Atlas connection
    if "mongodb+srv" in settings.MONGO_URI:
        options.update(
            {
                "tls": True,
                "tlsAllowInvalidCertificates": False,
            }
        )

    return options


async def init_db() -> None:
    """Initialize database connection with retry logic."""
    global _client

    max_retries = 3
    retry_delay = 1  # Initial delay in seconds

    for attempt in range(max_retries):
        try:
            if _client is None:
                _client = AsyncIOMotorClient(
                    settings.MONGO_URI,
                    **get_client_options(),
                )
            # Test the connection
            await _client.admin.command("ping")
            logger.info("Successfully connected to MongoDB")
            return
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            if attempt == max_retries - 1:
                logger.error(
                    "Failed to connect to MongoDB after %d attempts", max_retries
                )
                raise
            logger.warning(
                "Connection attempt %d failed, retrying in %d seconds: %s",
                attempt + 1,
                retry_delay,
                str(e),
            )
            await asyncio.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff
        except Exception as e:
            logger.error("Unexpected error connecting to MongoDB: %s", str(e))
            raise


def get_client() -> AsyncIOMotorClient:
    """Get MongoDB client instance.

    Returns:
        AsyncIOMotorClient: The MongoDB client instance.

    Raises:
        RuntimeError: If the client is not initialized.
    """
    if _client is None:
        raise RuntimeError("MongoDB client not initialized. Call init_db() first.")
    return _client


def get_db() -> AsyncIOMotorDatabase:
    """Get MongoDB database instance.

    Returns:
        AsyncIOMotorDatabase: The MongoDB database instance.

    Raises:
        RuntimeError: If the client is not initialized.
    """
    if _client is None:
        raise RuntimeError("MongoDB client not initialized. Call init_db() first.")
    return _client[settings.MONGO_DATABASE]
