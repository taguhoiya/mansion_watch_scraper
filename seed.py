#!/usr/bin/env python3
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

import motor.motor_asyncio
from pymongo.errors import (
    ConnectionFailure,
    OperationFailure,
    ServerSelectionTimeoutError,
)
from pymongo.server_api import ServerApi

from app.configs.settings import LOGGING_CONFIG
from app.db.session import get_client, init_db

# Configure structured logging
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# Environment variables
ENV = os.getenv("ENV", "development")
logger.info(f"Current environment: {ENV} (from ENV variable)")
logger.info(f"All environment variables: {dict(os.environ)}")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "mansion_watch")
COLLECTION_PROPERTIES = os.getenv("COLLECTION_PROPERTIES", "properties")
COLLECTION_USERS = os.getenv("COLLECTION_USERS", "users")
COLLECTION_USER_PROPERTIES = os.getenv("COLLECTION_USER_PROPERTIES", "user_properties")


async def check_environment() -> None:
    """Check if seeding is allowed in current environment."""
    current_env = ENV.lower()
    logger.info(f"Checking environment: {current_env}")

    if current_env == "production":
        logger.error(
            f"Seeding is not allowed in production environment (ENV={current_env})"
        )
        sys.exit(1)
    elif current_env not in ["development", "test", "docker"]:
        logger.error(
            f"Invalid environment: {current_env}. Must be one of: development, test, docker"
        )
        sys.exit(1)

    logger.info(f"Starting database seeding in {current_env} environment")


async def get_mongodb_client():
    """Create and return MongoDB client with proper settings."""
    client_settings = {
        "server_api": ServerApi("1"),
        "tls": False,
    }
    if "mongodb+srv" in MONGO_URI:
        client_settings["tls"] = True
        client_settings["tlsAllowInvalidCertificates"] = False

    return motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI, **client_settings)


async def check_existing_data(collections: dict) -> bool:
    """Check if collections already have data."""
    for name, collection in collections.items():
        if await collection.count_documents({}) > 0:
            logger.info(f"Collection {name} already has data, skipping seeding")
            return True
    return False


async def insert_sample_data(collections: dict) -> None:
    """Insert sample data into collections."""
    now = datetime.now(timezone.utc)

    # Insert user
    user_data = {"email": "admin@example.com", "created_at": now, "updated_at": now}
    user_result = await collections[COLLECTION_USERS].insert_one(user_data)

    # Insert property
    property_data = {
        "name": "Sample Property",
        "description": "A sample property for testing",
        "created_at": now,
        "updated_at": now,
    }
    property_result = await collections[COLLECTION_PROPERTIES].insert_one(property_data)

    # Insert user property
    user_property_data = {
        "user_id": user_result.inserted_id,
        "property_id": property_result.inserted_id,
        "created_at": now,
        "updated_at": now,
    }
    await collections[COLLECTION_USER_PROPERTIES].insert_one(user_property_data)


async def seed_database() -> None:
    """Seed the database with initial data."""
    await check_environment()

    try:
        # Initialize MongoDB connection
        await init_db()
        client = get_client()
        db = client[DB_NAME]
        collections = {
            COLLECTION_PROPERTIES: db[COLLECTION_PROPERTIES],
            COLLECTION_USERS: db[COLLECTION_USERS],
            COLLECTION_USER_PROPERTIES: db[COLLECTION_USER_PROPERTIES],
        }

        if await check_existing_data(collections):
            return

        logger.info("Seeding database...")
        await insert_sample_data(collections)
        logger.info("Database seeded successfully!")

    except ConnectionFailure as e:
        logger.error(f"Connection failure: {e}")
        raise
    except ServerSelectionTimeoutError as e:
        logger.error(f"Server selection timeout: {e}")
        raise
    except OperationFailure as e:
        logger.error(f"Operation failure: {e}")
        raise
    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        raise


async def main():
    """Main function to run the seed script."""
    try:
        await seed_database()
    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
