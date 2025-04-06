import base64
import http.server
import json
import logging
import os
from typing import Any, Dict, List

import pymongo

from app.configs.settings import LOGGING_CONFIG
from app.services.dates import get_current_time
from mansion_watch_scraper.pubsub.service import PubSubService

# Configure structured logging
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# Add module context to logger
logger = logging.LoggerAdapter(
    logger,
    {
        "component": "pubsub_health",
        "operation": "health_check",
        "user_id": None,  # Initialize with None
        "url": None,  # Initialize with None
    },
)

# Global variables for MongoDB connection
mongo_client = None
db = None

# Initialize PubSubService once
pubsub_service = PubSubService()


class UnifiedHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests for health checks."""
        logger.info(
            "Health check request received",
            extra={
                "operation": "health_check",
                "user_id": None,
                "url": None,
            },
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))

    def do_POST(self):
        """Handle POST requests for Pub/Sub push messages."""
        try:
            # Get content length
            content_length = int(self.headers.get("Content-Length", 0))

            # Read and parse request body
            body = self.rfile.read(content_length)

            try:
                body_json = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError as e:
                logger.error(
                    "Failed to decode JSON",
                    extra={
                        "operation": "pubsub_push",
                        "error": str(e),
                        "user_id": None,
                        "url": None,
                    },
                )
                self._send_error(400, "Invalid JSON payload")
                return

            # Extract the actual Pub/Sub message from the body
            try:
                if "message" not in body_json:
                    logger.error(
                        "No message field in request",
                        extra={
                            "operation": "pubsub_push",
                            "body": body_json,
                            "user_id": None,
                            "url": None,
                        },
                    )
                    self._send_error(400, "No message field in request")
                    return

                pubsub_message = body_json["message"]

                # Decode base64 data before parsing JSON
                encoded_data = pubsub_message.get("data", "{}")
                decoded_data = base64.b64decode(encoded_data).decode("utf-8")
                message_data = json.loads(decoded_data)

                user_id = message_data.get("line_user_id")
                url = message_data.get("url")

                # Update logger context
                logger.extra.update(
                    {
                        "user_id": user_id,
                        "url": url,
                    }
                )

                # Log based on message type
                if url and user_id:
                    logger.info(
                        "Processing Pub/Sub message for specific property",
                        extra={
                            "operation": "pubsub_push",
                            "message_id": pubsub_message.get("messageId", "unknown"),
                            "user_id": user_id,
                            "url": url,
                        },
                    )
                elif user_id:
                    logger.info(
                        "Processing Pub/Sub message for user batch",
                        extra={
                            "operation": "pubsub_push",
                            "message_id": pubsub_message.get("messageId", "unknown"),
                            "user_id": user_id,
                        },
                    )
                else:
                    logger.info(
                        "Processing Pub/Sub message for all users batch",
                        extra={
                            "operation": "pubsub_push",
                            "message_id": pubsub_message.get("messageId", "unknown"),
                        },
                    )

                # Use the global PubSubService instance
                pubsub_service.message_callback(pubsub_message)

                # Send success response
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))

            except Exception as e:
                logger.error(
                    "Error processing Pub/Sub message",
                    extra={
                        "operation": "pubsub_push",
                        "error": str(e),
                        "error_type": e.__class__.__name__,
                        "user_id": None,
                        "url": None,
                    },
                    exc_info=True,
                )
                self._send_error(500, f"Error processing message: {str(e)}")
                return

        except Exception as e:
            logger.error(
                "Error handling POST request",
                extra={
                    "operation": "pubsub_push",
                    "error": str(e),
                    "error_type": e.__class__.__name__,
                    "user_id": None,
                    "url": None,
                },
                exc_info=True,
            )
            self._send_error(500, f"Internal server error: {str(e)}")

    def _send_error(self, code: int, message: str):
        """Helper method to send error responses."""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps({"status": "error", "error": message}).encode("utf-8")
        )


def get_properties_for_batch(line_user_id: str = None) -> List[Dict[str, Any]]:
    """Get all properties that need to be processed in batch.

    Args:
        line_user_id: Optional LINE user ID to filter properties for a specific user

    Returns:
        List of ScrapeRequest-compatible dictionaries containing:
        - timestamp: Current time (ISO format string)
        - url: Property URL
        - line_user_id: User's LINE ID
        - check_only: True (only checking for updates)
    """
    db = get_db()
    user_properties_collection = db[os.getenv("COLLECTION_USER_PROPERTIES")]
    current_time = get_current_time()

    # Base match stage for aggregation pipeline
    match_stage = {"next_aggregated_at": {"$lte": current_time}}

    # Add line_user_id filter if provided
    if line_user_id:
        match_stage["line_user_id"] = line_user_id

    # Use aggregation pipeline to join collections and filter
    pipeline = [
        # First stage: Match user properties that need aggregation
        {"$match": match_stage},
        # Second stage: Group by property_id and preserve line_user_id
        {
            "$group": {
                "_id": "$property_id",
                "line_user_id": {"$first": "$line_user_id"},  # Keep the line_user_id
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
        # Fourth stage: Unwind the property array (from lookup)
        {"$unwind": "$property"},
        # Fifth stage: Filter active properties
        {"$match": {"property.is_active": True}},
        # Final stage: Project only the needed fields in ScrapeRequest format
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
                "line_user_id": 1,  # Use the preserved line_user_id
                "check_only": {"$literal": True},
            }
        },
    ]

    return list(user_properties_collection.aggregate(pipeline))


def check_user_exists(line_user_id: str) -> bool:
    """Check if a user exists in the database.

    Args:
        line_user_id: LINE user ID to check

    Returns:
        bool: True if user exists, False otherwise
    """
    db = get_db()
    users_collection = db[os.getenv("COLLECTION_USERS")]
    return users_collection.count_documents({"line_user_id": line_user_id}) > 0


def main():
    """Start the HTTP server."""
    try:
        logger.info("Starting main function")

        # Initialize the database connection
        init_db()  # Ensure this function is defined and initializes the MongoDB client

        port = int(os.environ.get("PORT", 8080))
        logger.info(f"Environment variables: {dict(os.environ)}")

        server = http.server.HTTPServer(("0.0.0.0", port), UnifiedHandler)
        logger.info(f"Server created, listening on 0.0.0.0:{port}")
        server.serve_forever()

    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}", exc_info=True)
        raise


def init_db():
    """Initialize the MongoDB client and database."""
    global mongo_client, db
    mongo_client = pymongo.MongoClient(os.getenv("MONGO_URI"))
    db = mongo_client[os.getenv("MONGO_DATABASE")]
    logger.info("MongoDB client and database initialized")


def get_db():
    """Get the MongoDB database instance.

    Returns:
        pymongo.database.Database: The MongoDB database instance
    """
    if "db" not in globals() or globals()["db"] is None:
        init_db()
    return globals()["db"]


if __name__ == "__main__":
    logger.info("Starting health check server")
    main()
