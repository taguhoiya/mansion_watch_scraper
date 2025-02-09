import os

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.database import Database
from pymongo.server_api import ServerApi

client = AsyncIOMotorClient(os.getenv("MONGO_URI"), server_api=ServerApi("1"))


def get_db() -> Database:
    """Get the database instance.

    Returns:
        Database: The database instance.
    """
    db: Database = client[os.getenv("MONGO_DATABASE")]
    return db
