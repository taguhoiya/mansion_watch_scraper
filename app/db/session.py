"""MongoDB session management module."""

import os
from typing import Any, Dict

import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.monitoring import register
from pymongo.server_api import ServerApi

from app.db.monitoring import PerformanceCommandListener

# Register performance monitoring listener
register(PerformanceCommandListener())


def get_client_options() -> Dict[str, Any]:
    """Get MongoDB client options.

    Returns:
        Dict[str, Any]: MongoDB client options
    """
    is_production = os.getenv("ENV") != "development" and os.getenv("ENV") != "docker"

    options = {
        "server_api": ServerApi("1"),
        "retryWrites": True,
        "maxPoolSize": int(os.getenv("MONGO_MAX_POOL_SIZE", "100")),
        "minPoolSize": int(os.getenv("MONGO_MIN_POOL_SIZE", "10")),
        "maxIdleTimeMS": int(os.getenv("MONGO_MAX_IDLE_TIME_MS", "30000")),
        "serverSelectionTimeoutMS": 30000,  # Increased timeout for server selection
        "connectTimeoutMS": int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "20000")),
        "waitQueueTimeoutMS": int(os.getenv("MONGO_WAIT_QUEUE_TIMEOUT_MS", "10000")),
        "heartbeatFrequencyMS": 10000,  # More frequent server checks
        "localThresholdMS": 15,  # Smaller threshold for selecting nearest server
    }

    if is_production:
        options.update(
            {
                "tls": True,
                "tlsCAFile": os.getenv("MONGO_CA_FILE", certifi.where()),
                "retryReads": True,
                "w": "majority",  # Write concern for better consistency
                "readPreference": "primaryPreferred",  # Read from primary when available
            }
        )

    return options


async def get_db() -> AsyncIOMotorDatabase:
    """Get MongoDB database instance.

    Returns:
        AsyncIOMotorDatabase: MongoDB database instance
    """
    client = AsyncIOMotorClient(os.getenv("MONGO_URI"), **get_client_options())
    return client[os.getenv("MONGO_DATABASE", "mansion_watch")]


async def init_db() -> AsyncIOMotorDatabase:
    """Initialize database connection and verify connectivity.

    Returns:
        AsyncIOMotorDatabase: The initialized database instance.

    Raises:
        Exception: If database connection fails.
    """
    try:
        client = AsyncIOMotorClient(os.getenv("MONGO_URI"), **get_client_options())
        db = client[os.getenv("MONGO_DATABASE", "mansion_watch")]
        # Verify database connection
        await client.admin.command("ping")
        return db
    except Exception as e:
        raise Exception(f"Failed to initialize database: {str(e)}")
