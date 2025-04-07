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

    def verify_cloud_run_authentication(self) -> bool:
        """Verify the request is from Cloud Run Pub/Sub push.

        Returns:
            bool: True if authenticated, False otherwise
        """
        auth_header = self.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            logger.error("Missing or invalid Authorization header")
            return False

        # In Cloud Run, authentication is handled automatically
        # If we receive the request, it means Cloud Run has already authenticated it
        return True

    def check_retry_count(self) -> bool:
        """Check if message has exceeded retry attempts.

        Cloud Run's Pub/Sub retry count is in the X-CloudPubSub-DeliveryAttempt header.
        After 5 retries (value of 6), we'll stop retrying to prevent excessive processing.

        Returns:
            bool: True if should continue processing, False if should stop
        """
        try:
            retry_count = int(self.headers.get("X-CloudPubSub-DeliveryAttempt", "1"))
            if retry_count > 5:  # Stop after 5 retries (less than Cloud Run's max of 7)
                logger.warning(
                    "Message exceeded retry limit",
                    extra={
                        "operation": "retry_check",
                        "retry_count": retry_count,
                    },
                )
                self._send_error(
                    429,  # Too Many Requests
                    "Message exceeded retry limit",
                    retry=False,
                )
                return False
            return True
        except ValueError:
            # If header is invalid, continue processing
            return True

    def _decode_pubsub_data(self, pubsub_message: dict, subscription: str) -> dict:
        """Decode the data field from a Pub/Sub message."""
        if subscription == "direct":
            return pubsub_message

        try:
            encoded_data = pubsub_message["data"]
            decoded_data = base64.b64decode(encoded_data).decode("utf-8")
            return json.loads(decoded_data)
        except Exception as e:
            logger.error(
                "Failed to decode message data",
                extra={
                    "error": str(e),
                    "error_type": e.__class__.__name__,
                    "encoded_data": pubsub_message.get("data"),
                },
            )
            raise ValueError(f"Invalid message data format: {str(e)}")

    def _validate_message_data(self, message_data: dict, subscription: str) -> None:
        """Validate required fields in message data."""
        if not isinstance(message_data, dict):
            logger.error(
                "Invalid message data format",
                extra={"subscription": subscription, "message_data": message_data},
            )
            raise ValueError("Invalid message data format")

        required_fields = ["timestamp", "url", "line_user_id"]
        missing_fields = [
            field for field in required_fields if field not in message_data
        ]
        if missing_fields:
            logger.error(
                "Missing required fields in message data",
                extra={
                    "subscription": subscription,
                    "missing_fields": missing_fields,
                    "message_data": message_data,
                },
            )
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    def parse_pubsub_message(self, body: bytes) -> tuple[dict, str, dict]:
        """Parse and validate the Pub/Sub message from request body."""
        try:
            body_json = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to decode JSON",
                extra={"error": str(e), "body": body.decode("utf-8", errors="ignore")},
            )
            raise ValueError("Invalid JSON payload")

        # Handle both direct messages and Pub/Sub push messages
        if isinstance(body_json, dict) and "message" in body_json:
            pubsub_message = body_json["message"]
            subscription = body_json.get("subscription", "unknown")
        else:
            pubsub_message = body_json
            subscription = "direct"

        if not isinstance(pubsub_message, dict):
            raise ValueError("Invalid message format")

        message_data = self._decode_pubsub_data(pubsub_message, subscription)
        self._validate_message_data(message_data, subscription)

        return pubsub_message, subscription, message_data

    def log_message_processing(
        self, message_data: dict, pubsub_message: dict, subscription: str
    ) -> None:
        """Log appropriate message based on the message type."""
        user_id = message_data.get("line_user_id")
        url = message_data.get("url")

        # Update logger context
        logger.extra.update({"user_id": user_id, "url": url})

        log_extra = {
            "operation": "pubsub_push",
            "message_id": pubsub_message.get("messageId"),
            "subscription": subscription,
        }

        if url and user_id:
            log_extra.update({"user_id": user_id, "url": url})
            logger.info(
                "Processing Pub/Sub message for specific property", extra=log_extra
            )
        elif user_id:
            log_extra.update({"user_id": user_id})
            logger.info("Processing Pub/Sub message for user batch", extra=log_extra)
        else:
            logger.info(
                "Processing Pub/Sub message for all users batch", extra=log_extra
            )

    def do_POST(self):
        """Handle POST requests for Pub/Sub push messages."""
        try:
            # Verify Cloud Run authentication
            if not self.verify_cloud_run_authentication():
                self._send_error(403, "Unauthorized")
                return

            # Check retry count
            if not self.check_retry_count():
                return

            # Get content length and validate
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._send_error(400, "Empty request body", retry=False)
                return

            # Read request body
            body = self.rfile.read(content_length)

            try:
                # Parse and validate message
                pubsub_message, subscription, message_data = self.parse_pubsub_message(
                    body
                )

                # Log message processing
                self.log_message_processing(message_data, pubsub_message, subscription)

                # Process the message - pass the entire body_json
                body_json = json.loads(body.decode("utf-8"))
                pubsub_service.message_callback(body_json)

                # Send success response
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))

            except ValueError as e:
                # Handle validation errors - don't retry
                self._send_error(400, str(e), retry=False)
            except Exception as e:
                # Handle processing errors - allow retry
                logger.error(
                    "Error processing Pub/Sub message",
                    extra={
                        "operation": "pubsub_push",
                        "error": str(e),
                        "error_type": e.__class__.__name__,
                        "message_id": (
                            pubsub_message.get("messageId")
                            if "pubsub_message" in locals()
                            else None
                        ),
                        "subscription": (
                            subscription if "subscription" in locals() else None
                        ),
                    },
                    exc_info=True,
                )
                self._send_error(500, f"Error processing message: {str(e)}", retry=True)

        except Exception as e:
            # Handle unexpected errors - allow retry
            logger.error(
                "Error handling POST request",
                extra={
                    "operation": "pubsub_push",
                    "error": str(e),
                    "error_type": e.__class__.__name__,
                },
                exc_info=True,
            )
            self._send_error(500, f"Internal server error: {str(e)}", retry=True)

    def _send_error(self, code: int, message: str, retry: bool = True):
        """Helper method to send error responses with retry control.

        According to Cloud Pub/Sub documentation, to prevent message retries and acknowledge
        the message as processed (even if failed), we should:
        1. Return a 200 status code
        2. Set X-CloudPubSub-DeliveryAttempt header

        Args:
            code: HTTP status code (will be ignored for Pub/Sub messages)
            message: Error message
            retry: Whether Pub/Sub should retry the message (ignored, always set to false)
        """
        # For Pub/Sub messages, always return 200 to acknowledge the message
        self.send_response(200)
        self.send_header("Content-Type", "application/json")

        # Tell Pub/Sub not to retry by setting the delivery attempt header
        self.send_header("X-CloudPubSub-DeliveryAttempt", "1")

        self.end_headers()
        self.wfile.write(
            json.dumps(
                {"status": "error", "error": message, "original_status_code": code}
            ).encode("utf-8")
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
