import os

import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.database import Database
from pymongo.server_api import ServerApi


def get_client_options():
    """Get MongoDB client options based on environment."""
    is_production = os.getenv("ENV") != "development" and os.getenv("ENV") != "docker"

    options = {
        "server_api": ServerApi("1"),
    }

    if is_production:
        options.update(
            {
                "tls": True,
                "tlsCAFile": certifi.where(),
                "retryWrites": True,
                "w": "majority",
                "appName": "MansionWatch",
            }
        )

    return options


# Initialize MongoDB client with appropriate options
client = AsyncIOMotorClient(os.getenv("MONGO_URI"), **get_client_options())


def get_db() -> Database:
    """Get the database instance.

    Returns:
        Database: The database instance.
    """
    db_name = os.getenv("MONGO_DATABASE", "mansionwatch")
    if not db_name:
        raise ValueError("MONGO_DATABASE environment variable is not set")

    db: Database = client[db_name]
    return db
