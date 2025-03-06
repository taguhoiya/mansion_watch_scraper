#!/usr/bin/env python3
import asyncio
import logging
import os
from datetime import datetime

import motor.motor_asyncio
from bson import ObjectId
from pymongo.server_api import ServerApi

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "mansion_watch")
COLLECTION_USERS = os.getenv("COLLECTION_USERS", "users")
COLLECTION_PROPERTIES = os.getenv("COLLECTION_PROPERTIES", "properties")
COLLECTION_USER_PROPERTIES = os.getenv("COLLECTION_USER_PROPERTIES", "user_properties")


async def seed_database():
    """Seed the database with sample data."""
    logger.info(f"Connecting to MongoDB at {MONGO_URI}")
    client = motor.motor_asyncio.AsyncIOMotorClient(
        MONGO_URI, server_api=ServerApi("1")
    )
    db = client[MONGO_DATABASE]

    # Check if collections already have data
    users_count = await db[COLLECTION_USERS].count_documents({})
    properties_count = await db[COLLECTION_PROPERTIES].count_documents({})

    if users_count > 0 or properties_count > 0:
        logger.info("Database already has data. Skipping seeding.")
        return

    logger.info("Seeding database with sample data...")

    # Sample user data
    now = datetime.utcnow()
    user_id = ObjectId()
    user = {
        "_id": user_id,
        "line_user_id": "U23b619197d01bab29b2c54955db6c2a1",
        "created_at": now,
        "updated_at": now,
    }

    # Sample property data
    property_id = ObjectId()
    property_data = {
        "_id": property_id,
        "name": "クレヴィア渋谷富ヶ谷",
        "url": "https://suumo.jp/ms/chuko/tokyo/sc_shibuya/nc_76483805/",
        "is_active": True,
        "large_property_description": "２沿線以上利用可、スーパー 徒歩10分以内、小学校 徒歩10分以内、駐輪場",
        "small_property_description": "◎戸建感覚を演出するメゾネット<br>◎スキップフロアのある、立体的な空間構成の2LDK<br>◎各洋室2面採光<br>◎屋上は開放感のあるルーフテラス<br>◎西森事務所によるデザイナーズ設計",
        "created_at": now,
        "updated_at": now,
        "image_urls": [
            "https://storage.cloud.google.com/mansion_watch/property_images/sample1.jpg",
            "https://storage.cloud.google.com/mansion_watch/property_images/sample2.jpg",
        ],
    }

    # Sample user_property data
    user_property = {
        "_id": ObjectId(),
        "user_id": user_id,
        "property_id": property_id,
        "is_favorite": True,
        "created_at": now,
        "updated_at": now,
    }

    # Insert data
    await db[COLLECTION_USERS].insert_one(user)
    await db[COLLECTION_PROPERTIES].insert_one(property_data)
    await db[COLLECTION_USER_PROPERTIES].insert_one(user_property)

    logger.info("Database seeded successfully!")


async def main():
    """Main function to run the seed script."""
    try:
        await seed_database()
    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
