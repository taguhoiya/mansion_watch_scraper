import base64
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional, Union

from google.auth.transport import requests
from google.oauth2 import id_token

from mansion_watch_scraper.models.property import Property
from mansion_watch_scraper.models.user_property import UserProperty
from mansion_watch_scraper.utils.mongo import get_mongo_client

logger = logging.getLogger(__name__)


class UnifiedHandler(BaseHTTPRequestHandler):
    def _add_cors_headers(self):
        """Add CORS headers to the response"""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Credentials", "false")

    def _send_response(self, status_code: int, data: Dict = None):
        """Send response with CORS headers"""
        self.send_response(status_code)
        self._add_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if data:
            self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self._send_response(200)

    def do_GET(self):
        """Handle GET requests for health checks"""
        self._send_response(200, {"status": "ok"})

    def do_POST(self):
        """Handle POST requests for Pub/Sub messages"""
        try:
            # Verify Cloud Run authentication
            auth_header = self.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                self._send_response(401, {"error": "No credentials provided"})
                return

            token = auth_header.split(" ")[1]
            try:
                audience = os.getenv("CLOUD_RUN_URL")
                claims = id_token.verify_oauth2_token(
                    token, requests.Request(), audience=audience
                )
                if not claims.get("email_verified"):
                    self._send_response(401, {"error": "Email not verified"})
                    return
            except Exception as e:
                logger.error(f"Token verification failed: {e}")
                self._send_response(401, {"error": "Invalid credentials"})
                return

            # Check retry count
            retry_count = int(self.headers.get("Ce-Retrycount", "0"))
            if retry_count > 5:
                logger.warning(f"Too many retries ({retry_count}), dropping message")
                self._send_response(200)
                return

            # Get message data
            content_length = int(self.headers.get("Content-Length", 0))
            message_data = self.rfile.read(content_length)
            message = json.loads(message_data)

            if not message.get("message", {}).get("data"):
                self._send_response(400, {"error": "No message data"})
                return

            # Decode Pub/Sub data
            pubsub_data = base64.b64decode(message["message"]["data"]).decode()
            data = json.loads(pubsub_data)

            # Process message
            logger.info(f"Processing message: {data}")
            process_message(data)

            self._send_response(200, {"status": "success"})

        except Exception as e:
            logger.error(f"Error processing request: {e}")
            self._send_response(500, {"error": str(e)})


def init_mongo():
    """Initialize MongoDB connection"""
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        logger.error("MONGO_URI environment variable not set")
        sys.exit(1)

    try:
        client = get_mongo_client()
        db = client.get_default_database()
        logger.info("Connected to MongoDB")
        return db
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)


def get_properties_for_batch(
    db, line_user_id: Optional[str] = None
) -> List[Union[Property, UserProperty]]:
    """Get properties for batch processing"""
    try:
        if line_user_id:
            # Get properties for specific user
            collection = db.user_properties
            query = {"line_user_id": line_user_id}
        else:
            # Get all properties
            collection = db.properties
            query = {}

        properties = list(collection.find(query))
        logger.info(f"Found {len(properties)} properties for batch processing")
        return properties
    except Exception as e:
        logger.error(f"Error getting properties for batch: {e}")
        return []


def process_message(data: Dict):
    """Process Pub/Sub message"""
    try:
        db = init_mongo()
        line_user_id = data.get("line_user_id")
        check_only = data.get("check_only", False)

        properties = get_properties_for_batch(db, line_user_id)
        if not properties:
            logger.warning("No properties found for batch processing")
            return

        if check_only:
            logger.info("Check only mode, skipping updates")
            return

        # Process properties (implementation depends on your needs)
        for property in properties:
            logger.info(f"Processing property: {property.get('_id')}")
            # Add your property processing logic here

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise


def run_server(port: int):
    """Run the HTTP server"""
    server = HTTPServer(("", port), UnifiedHandler)
    logger.info(f"Starting server on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(os.getenv("PORT", "8080"))
    run_server(port)