import os

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.database import Database
from pymongo.server_api import ServerApi

# TODO: Use certifi to verify the SSL certificate
client = AsyncIOMotorClient(os.getenv("MONGO_URI"), server_api=ServerApi("1"))


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
