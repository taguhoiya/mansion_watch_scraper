import http.server
import json
import logging
import os
import sys
from typing import Any, Dict, List

import pymongo
from google.cloud import pubsub_v1

from app.services.dates import get_current_time
from mansion_watch_scraper.pubsub.service import PubSubService

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Global variables for MongoDB connection
mongo_client = None
db = None

# Initialize PubSubService once
pubsub_service = PubSubService()


class HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle health check requests."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))

    def do_POST(self):
        """Handle Pub/Sub push messages."""
        try:
            # Get content length
            content_length = int(self.headers.get("Content-Length", 0))

            # Read and parse request body
            body = self.rfile.read(content_length)
            try:
                body_json = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON: {e}")
                self._send_error(400, "Invalid JSON payload")
                return

            # Log received message
            logger.info("Received push message")

            # Extract the actual Pub/Sub message from the body
            try:
                if "message" not in body_json:
                    self._send_error(400, "No message field in request")
                    return

                pubsub_message = body_json["message"]

                # Use the global PubSubService instance
                pubsub_service.message_callback(pubsub_message)

                # Send success response
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))

            except Exception as e:
                logger.error(f"Error processing Pub/Sub message: {e}")
                self._send_error(500, f"Error processing message: {str(e)}")
                return

        except Exception as e:
            logger.error(f"Error handling POST request: {e}")
            self._send_error(500, f"Internal server error: {str(e)}")

    def _send_error(self, code: int, message: str):
        """Helper method to send error responses."""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps({"status": "error", "error": message}).encode("utf-8")
        )


def publish_property_messages(
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
                "check_only": True,
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
    """Handler for batch processing requests."""

    def do_POST(self):
        """Handle batch processing requests."""
        try:
            # Parse query parameters if any
            from urllib.parse import parse_qs, urlparse

            query_components = parse_qs(urlparse(self.path).query)

            # Get line_user_id from query parameters if present
            line_user_id = query_components.get("line_user_id", [None])[0]
            logger.info(f"Processing batch request with line_user_id: {line_user_id}")

            # Check if user exists when line_user_id is provided
            if line_user_id and not check_user_exists(line_user_id):
                logger.warning(f"User with LINE ID {line_user_id} not found")
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {
                            "status": "error",
                            "message": f"User with LINE ID {line_user_id} not found",
                        }
                    ).encode("utf-8")
                )
                return

            # Get the topic path from environment
            project_id = os.getenv("GCP_PROJECT_ID")
            topic_id = os.getenv("PUBSUB_TOPIC")
            topic_path = f"projects/{project_id}/topics/{topic_id}"

            # Get properties that need processing
            properties = get_properties_for_batch(line_user_id)

            if not properties:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                message = "No properties to process"
                if line_user_id:
                    message += f" for user {line_user_id}"
                self.wfile.write(
                    json.dumps({"status": "success", "message": message}).encode(
                        "utf-8"
                    )
                )
                return

            # Publish messages for each property
            publish_property_messages(properties, topic_path)

            logger.info(
                f"Published messages for {len(properties)} urls: {[prop['url'] for prop in properties]}"
            )

            # Send success response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            message = f"Published messages for {len(properties)} properties"
            if line_user_id:
                message += f" for user {line_user_id}"
            self.wfile.write(
                json.dumps(
                    {
                        "status": "success",
                        "message": message,
                    }
                ).encode("utf-8")
            )

        except Exception as e:
            logger.error(f"Error in batch processing: {e}")
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
                logger.info(f"Received POST request to path: {parsed_path}")

                if parsed_path == "/health":
                    return HealthHandler.do_POST(self)
                elif parsed_path == "/batch":
                    return BatchHandler.do_POST(self)
                else:
                    logger.warning(f"404 Not Found for path: {parsed_path}")
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
