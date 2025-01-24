import os

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.database import Database

client = AsyncIOMotorClient(os.getenv("MONGO_URI"))


def get_db() -> Database:
    """Get the database instance.

    Returns:
        Database: The database instance.
    """
    db: Database = client[os.getenv("MONGO_DATABASE")]
    return db
