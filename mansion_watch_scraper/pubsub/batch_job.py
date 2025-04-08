import json
import logging
import logging.config
import os
from typing import Any, Dict, List

import pymongo
from google.cloud import pubsub_v1

from app.configs.settings import LOGGING_CONFIG
from app.services.dates import get_current_time

# Configure structured logging
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# Add module context to logger
logger = logging.LoggerAdapter(
    logger,
    {
        "component": "batch_job",
        "operation": "batch_processing",
    },
)


def init_db():
    """Initialize MongoDB connection."""
    mongo_client = pymongo.MongoClient(os.getenv("MONGO_URI"))
    db = mongo_client[os.getenv("MONGO_DATABASE")]
    logger.info("MongoDB client and database initialized")
    return db


def get_properties_for_batch(db) -> List[Dict[str, Any]]:
    """Get all properties that need processing based on next_aggregated_at time.

    Args:
        db: MongoDB database instance

    Returns:
        List[Dict[str, Any]]: List of property data for batch processing
    """
    user_properties_collection = db[os.getenv("COLLECTION_USER_PROPERTIES")]
    current_time = get_current_time()

    pipeline = [
        # First stage: Match properties that need aggregation
        {"$match": {"next_aggregated_at": {"$lte": current_time}}},
        # Second stage: Group by property_id and preserve line_user_id
        {
            "$group": {
                "_id": "$property_id",
                "line_user_id": {"$first": "$line_user_id"},
            }
        },
        # Third stage: Join with properties collection
        {
            "$lookup": {
                "from": os.getenv("COLLECTION_PROPERTIES"),
                "localField": "_id",
                "foreignField": "_id",
                "as": "property",
            }
        },
        # Fourth stage: Unwind the property array
        {"$unwind": "$property"},
        # Fifth stage: Filter active properties
        {"$match": {"property.is_active": True}},
        # Final stage: Project needed fields
        {
            "$project": {
                "_id": 0,
                "timestamp": {
                    "$dateToString": {
                        "format": "%Y-%m-%dT%H:%M:%S.%LZ",
                        "date": current_time,
                    }
                },
                "url": "$property.url",
                "line_user_id": 1,
                "check_only": {"$literal": True},
            }
        },
    ]

    return list(user_properties_collection.aggregate(pipeline))


def publish_batch_message(properties: List[Dict[str, Any]]) -> None:
    """Publish batch messages to Pub/Sub.

    Args:
        properties: List of property data to publish
    """
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(
        os.getenv("GCP_PROJECT_ID"), os.getenv("PUBSUB_TOPIC")
    )

    # Group properties by user
    users_properties = {}
    for prop in properties:
        user_id = prop["line_user_id"]
        if user_id not in users_properties:
            users_properties[user_id] = []
        users_properties[user_id].append(prop)

    # Send one message per user
    for user_id, user_properties in users_properties.items():
        try:
            # Create message data for all user's properties
            message_data = {
                "timestamp": user_properties[0][
                    "timestamp"
                ],  # Use timestamp from first property
                "check_only": True,
                "line_user_id": user_id,
            }

            # Convert to string and encode
            data = json.dumps(message_data).encode("utf-8")
            future = publisher.publish(topic_path, data)
            future.result()  # Wait for message to be published
            logger.info(
                "Published batch message to Pub/Sub",
                extra={
                    "operation": "batch_publish",
                    "line_user_id": user_id,
                    "properties_count": len(user_properties),
                },
            )
        except Exception as e:
            logger.error(
                f"Failed to publish message: {str(e)}",
                extra={
                    "operation": "batch_publish",
                    "line_user_id": user_id,
                },
                exc_info=True,
            )


def main():
    """Main batch job function that processes all properties needing updates."""
    try:
        # Initialize database
        db = init_db()

        # Start batch processing
        logger.info("Starting batch processing")

        # Get all properties that need processing
        properties = get_properties_for_batch(db)
        if not properties:
            logger.info("No properties to process")
            return

        # Group properties by line_user_id for better logging
        properties_count = {}
        for prop in properties:
            user_id = prop["line_user_id"]
            properties_count[user_id] = properties_count.get(user_id, 0) + 1

        # Log summary
        for user_id, count in properties_count.items():
            logger.info(
                f"Found {count} properties to process for user {user_id}",
                extra={"line_user_id": user_id},
            )

        # Publish messages
        publish_batch_message(properties)

    except Exception as e:
        logger.error(f"Batch job failed: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
