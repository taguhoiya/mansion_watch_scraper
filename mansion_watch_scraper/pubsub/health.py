import http.server
import json
import logging
import os
from typing import Any, Dict, List

import pymongo
from google.cloud import pubsub_v1

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


class HealthHandler(http.server.BaseHTTPRequestHandler):
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
                import base64

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

                logger.info(
                    "Processing Pub/Sub message",
                    extra={
                        "operation": "pubsub_push",
                        "message_id": pubsub_message.get("messageId", "unknown"),
                        "user_id": user_id,
                        "url": url,
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


def publish_property_messages_for_batch(
    properties: List[Dict[str, Any]], topic_path: str
) -> None:
    """Publish messages for each property to PubSub topic.

    Args:
        properties: List of property documents from MongoDB
        topic_path: Full path to the PubSub topic
    """
    publisher = pubsub_v1.PublisherClient()

    for prop in properties:
        try:
            current_time = get_current_time()
            # Create message data
            message = {
                "timestamp": current_time.isoformat(),  # Convert datetime to ISO format string
                "url": prop["url"],
                "line_user_id": prop["line_user_id"],
                "check_only": True,  # Always True because this method is called when batch updating all props on the UI and using a batch job
            }

            # Publish message
            future = publisher.publish(topic_path, json.dumps(message).encode("utf-8"))

            # Wait for message to be published
            future.result()

        except Exception as e:
            logger.error(
                f"Error publishing message for property with URL {prop['url']}: {e}"
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


class BatchHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        """Handle batch processing requests with JSON payload."""
        try:
            # Validate Content-Type header
            content_type = self.headers.get("Content-Type", "")
            if content_type != "application/json":
                logger.error(
                    "Invalid Content-Type",
                    extra={
                        "operation": "batch_request_validation",
                        "content_type": content_type,
                        "user_id": None,
                        "url": None,
                    },
                )
                self._send_error(400, "Content-Type must be application/json")
                return

            # Read and parse JSON payload
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                logger.error(
                    "Missing request body",
                    extra={
                        "operation": "batch_request_validation",
                        "user_id": None,
                        "url": None,
                    },
                )
                self._send_error(400, "Missing request body")
                return

            try:
                payload = json.loads(self.rfile.read(content_length))
            except json.JSONDecodeError:
                logger.error(
                    "Invalid JSON payload",
                    extra={
                        "operation": "batch_request_validation",
                        "user_id": None,
                        "url": None,
                    },
                )
                self._send_error(400, "Invalid JSON payload")
                return

            line_user_id = payload.get("line_user_id")

            # Update logger context with user_id
            logger.extra.update(
                {
                    "user_id": line_user_id,
                }
            )

            logger.info(
                "Processing batch request",
                extra={
                    "operation": "batch_process",
                    "user_id": line_user_id,
                    "url": None,
                },
            )

            # Check if user exists when line_user_id is provided
            if line_user_id and not check_user_exists(line_user_id):
                logger.warning(
                    "User not found",
                    extra={
                        "operation": "batch_user_validation",
                        "user_id": line_user_id,
                        "url": None,
                    },
                )
                self._send_error(404, f"User with LINE ID {line_user_id} not found")
                return

            # Get properties to process
            properties = get_properties_for_batch(line_user_id)
            if not properties:
                logger.info(
                    "No properties to process",
                    extra={
                        "operation": "batch_process",
                        "user_id": line_user_id,
                        "url": None,
                    },
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"status": "success", "message": "No properties to process"}
                    ).encode("utf-8")
                )
                return

            # Get the topic path from environment
            project_id = os.getenv("GCP_PROJECT_ID")
            topic_id = os.getenv("PUBSUB_TOPIC")
            topic_path = f"projects/{project_id}/topics/{topic_id}"

            # Publish messages for each property
            publish_property_messages_for_batch(properties, topic_path)

            urls = [prop["url"] for prop in properties]
            url_count = len(urls)
            url_summary = (
                f"{urls[0]}... (+{url_count-1} more)"
                if url_count > 1
                else urls[0] if url_count == 1 else None
            )

            # Update logger context with urls
            logger.extra.update(
                {
                    "url": url_summary,
                }
            )

            logger.info(
                "Published batch messages",
                extra={
                    "operation": "batch_publish",
                    "property_count": len(properties),
                    "urls": urls,  # Keep full list in urls field for debugging if needed
                    "user_id": line_user_id,
                    "url": url_summary,
                },
            )

            # Send success response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "status": "success",
                        "message": f"Batch processing started for {len(properties)} properties",
                        "properties": len(properties),
                    }
                ).encode("utf-8")
            )

        except Exception as e:
            logger.error(
                "Error processing batch request",
                extra={
                    "operation": "batch_process_error",
                    "error": str(e),
                    "error_type": e.__class__.__name__,
                    "user_id": (line_user_id if "line_user_id" in locals() else None),
                },
                exc_info=True,
            )
            self._send_error(500, f"Internal server error: {str(e)}")


def main():
    """Start the HTTP server."""
    try:
        logger.info("Starting main function")

        # Initialize the database connection
        init_db()  # Ensure this function is defined and initializes the MongoDB client

        port = int(os.environ.get("PORT", 8080))
        logger.info(f"Environment variables: {dict(os.environ)}")

        # Create server with both handlers
        class CombinedHandler(HealthHandler, BatchHandler):
            def do_POST(self):
                from urllib.parse import urlparse

                parsed_path = urlparse(self.path).path

                # Update logger context with the current operation
                operation = (
                    "health_check"
                    if parsed_path == "/health"
                    else "batch_process" if parsed_path == "/batch" else "unknown"
                )
                logger.extra.update(
                    {
                        "operation": operation,
                        "user_id": None,
                        "url": None,
                    }
                )

                logger.info(f"Received POST request to path: {parsed_path}")

                if parsed_path == "/health":
                    return HealthHandler.do_POST(self)
                elif parsed_path == "/batch":
                    return BatchHandler.do_POST(self)
                else:
                    logger.warning(
                        f"404 Not Found for path: {parsed_path}",
                        extra={
                            "operation": "unknown",
                            "user_id": None,
                            "url": None,
                        },
                    )
                    self.send_error(404, "Not Found")

        server = http.server.HTTPServer(("0.0.0.0", port), CombinedHandler)
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
