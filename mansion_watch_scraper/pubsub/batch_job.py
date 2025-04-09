import json
import logging
import logging.config
import os

import pymongo
from google.auth import default
from google.cloud import pubsub_v1

from app.configs.settings import LOGGING_CONFIG
from app.services.dates import get_current_time

# Configure logging
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# Add module context to logger
logger = logging.LoggerAdapter(
    logger,
    {
        "component": "batch_job",
        "operation": "batch_processing",
        "labels": {
            "service": "Mansion Watch Scraper",
            "environment": os.getenv("ENV", "production"),
            "component": "batch_job",
        },
        "serviceContext": {"service": "Mansion Watch Scraper", "version": "1.0"},
    },
)


def init_mongodb():
    """Initialize MongoDB connection."""
    try:
        # Get MongoDB connection parameters from environment
        uri = os.getenv("MONGO_URI")
        if not uri:
            raise ValueError("MONGO_URI environment variable is not set")

        # Initialize MongoDB client with connection pooling settings
        client = pymongo.MongoClient(
            uri,
            maxPoolSize=int(os.getenv("MONGO_MAX_POOL_SIZE", "50")),
            minPoolSize=int(os.getenv("MONGO_MIN_POOL_SIZE", "0")),
            maxIdleTimeMS=int(os.getenv("MONGO_MAX_IDLE_TIME_MS", "10000")),
            connectTimeoutMS=int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "20000")),
            waitQueueTimeoutMS=int(os.getenv("MONGO_WAIT_QUEUE_TIMEOUT_MS", "10000")),
        )

        # Get database
        db_name = os.getenv("MONGO_DATABASE")
        if not db_name:
            raise ValueError("MONGO_DATABASE environment variable is not set")

        db = client[db_name]

        # Test connection
        client.admin.command("ping")
        logger.info("Successfully connected to MongoDB")

        return db
    except Exception as e:
        logger.error(
            f"Failed to initialize MongoDB: {str(e)}",
            extra={
                "error": str(e),
                "error_type": e.__class__.__name__,
            },
            exc_info=True,
        )
        raise


def get_user_ids(db):
    """Get all unique line_user_ids from user_properties collection."""
    try:
        collection = db[os.getenv("COLLECTION_USER_PROPERTIES", "user_properties")]
        user_ids = list(collection.distinct("line_user_id"))
        logger.info(f"Retrieved {len(user_ids)} unique user IDs")
        return user_ids
    except Exception as e:
        logger.error(
            f"Failed to get user IDs: {str(e)}",
            extra={
                "error": str(e),
                "error_type": e.__class__.__name__,
            },
            exc_info=True,
        )
        raise


def publish_message_for_user(publisher, topic_path, line_user_id):
    """Publish a message for a single user to Pub/Sub."""
    try:
        # Create message data
        data = {
            "timestamp": get_current_time().isoformat(),
            "check_only": True,
            "line_user_id": line_user_id,
        }

        # Convert to JSON string and encode
        message_bytes = json.dumps(data).encode("utf-8")

        # Publish message with retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Publish message
                future = publisher.publish(
                    topic_path,
                    message_bytes,
                    # ordering_key=line_user_id
                )
                published_message_id = (
                    future.result()
                )  # Wait for message to be published
                logger.info(
                    f"Published message for user {line_user_id}",
                    extra={
                        "operation": "user_publish",
                        "line_user_id": line_user_id,
                        "message_id": published_message_id,
                    },
                )
                return True
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(
                    f"Publish attempt {attempt + 1} failed for user {line_user_id}, retrying...",
                    extra={
                        "error": str(e),
                        "line_user_id": line_user_id,
                    },
                )
        return False

    except Exception as e:
        logger.error(
            f"Failed to publish message for user {line_user_id}: {str(e)}",
            extra={
                "error": str(e),
                "error_type": e.__class__.__name__,
                "line_user_id": line_user_id,
            },
            exc_info=True,
        )
        return False


def publish_batch_messages(user_ids):
    """Publish individual messages for each user to Pub/Sub."""
    try:
        # Get Pub/Sub settings from environment
        project_id = os.getenv("GCP_PROJECT_ID")
        topic_name = os.getenv("PUBSUB_TOPIC")

        if not project_id or not topic_name:
            raise ValueError("GCP_PROJECT_ID and PUBSUB_TOPIC must be set")

        # Get default credentials
        credentials, project = default()

        # Create publisher with explicit credentials
        publisher = pubsub_v1.PublisherClient(credentials=credentials)
        topic_path = publisher.topic_path(project_id, topic_name)

        successful_publishes = 0
        failed_publishes = 0

        # Process each user ID individually
        for line_user_id in user_ids:
            if publish_message_for_user(publisher, topic_path, line_user_id):
                successful_publishes += 1
            else:
                failed_publishes += 1

        # Log summary
        logger.info(
            f"Batch publishing completed. Success: {successful_publishes}, Failed: {failed_publishes}",
            extra={
                "operation": "batch_summary",
                "successful_publishes": successful_publishes,
                "failed_publishes": failed_publishes,
                "total_users": len(user_ids),
            },
        )

    except Exception as e:
        logger.error(
            f"Failed to process batch messages: {str(e)}",
            extra={
                "error": str(e),
                "error_type": e.__class__.__name__,
            },
            exc_info=True,
        )
        raise


def main():
    """Main batch job function."""
    try:
        logger.info("Starting batch job")

        # Initialize MongoDB
        db = init_mongodb()
        logger.info("MongoDB client and database initialized")

        # Get all user IDs
        user_ids = get_user_ids(db)
        if not user_ids:
            logger.warning("No user IDs found in database")
            return

        # Publish individual messages for each user
        publish_batch_messages(user_ids)
        logger.info("Batch job completed successfully")

    except Exception as e:
        logger.error(
            f"Batch job failed: {str(e)}",
            extra={
                "error": str(e),
                "error_type": e.__class__.__name__,
            },
            exc_info=True,
        )
        raise


if __name__ == "__main__":
    main()
