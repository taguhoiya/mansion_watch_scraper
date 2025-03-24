import http.server
import json
import logging
import os
import sys

from mansion_watch_scraper.pubsub.service import PubSubService

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

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


def main():
    """Start the HTTP server."""
    try:
        logger.info("Starting main function")
        port = int(os.environ.get("PORT", 8080))
        logger.info(f"Configured port: {port}")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Environment variables: {dict(os.environ)}")

        server = http.server.HTTPServer(("0.0.0.0", port), HealthHandler)
        logger.info(f"Server created, listening on 0.0.0.0:{port}")

        server.serve_forever()
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    logger.info("Starting health check server")
    main()
