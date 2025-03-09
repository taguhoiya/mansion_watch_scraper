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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Environment variables
ENV = os.getenv("ENV", "development")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "mansion_watch")
COLLECTION_PROPERTIES = os.getenv("COLLECTION_PROPERTIES", "properties")
COLLECTION_USERS = os.getenv("COLLECTION_USERS", "users")
COLLECTION_USER_PROPERTIES = os.getenv("COLLECTION_USER_PROPERTIES", "user_properties")


async def seed_database() -> None:
    """Seed the database with initial data."""
    # Check environment first
    if os.getenv("ENV") == "production":
        logger.error("Seeding is not allowed in production environment")
        sys.exit(1)

    logger.info(
        f"Starting database seeding in {os.getenv('ENV', 'development')} environment"
    )

    # MongoDB connection settings
    client_settings = {
        "server_api": ServerApi("1"),
        "tls": False,  # Default TLS setting
    }

    # Add TLS settings only for Atlas connections
    if "mongodb+srv" in MONGO_URI:
        client_settings["tls"] = True
        client_settings["tlsAllowInvalidCertificates"] = False

    try:
        client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI, **client_settings)

        db = client[DB_NAME]

        # Check if collections already have data
        collections = {
            COLLECTION_PROPERTIES: db[COLLECTION_PROPERTIES],
            COLLECTION_USERS: db[COLLECTION_USERS],
            COLLECTION_USER_PROPERTIES: db[COLLECTION_USER_PROPERTIES],
        }

        for name, collection in collections.items():
            if await collection.count_documents({}) > 0:
                logger.info(f"Collection {name} already has data, skipping seeding")
                return

        logger.info("Seeding database...")

        # Sample user data
        now = datetime.now(timezone.utc)
        user_data = {
            "email": "admin@example.com",
            "created_at": now,
            "updated_at": now,
        }

        # Insert user data
        user_result = await collections[COLLECTION_USERS].insert_one(user_data)
        user_id = user_result.inserted_id

        # Sample property data
        property_data = {
            "name": "Sample Property",
            "description": "A sample property for testing",
            "created_at": now,
            "updated_at": now,
        }

        # Insert property data
        property_result = await collections[COLLECTION_PROPERTIES].insert_one(
            property_data
        )
        property_id = property_result.inserted_id

        # Sample user property data
        user_property_data = {
            "user_id": user_id,
            "property_id": property_id,
            "created_at": now,
            "updated_at": now,
        }

        # Insert user property data
        await collections[COLLECTION_USER_PROPERTIES].insert_one(user_property_data)

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
