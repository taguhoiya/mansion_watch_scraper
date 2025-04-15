import logging
import logging.config
import os
from http.server import ThreadingHTTPServer

from app.configs.settings import LOGGING_CONFIG
from mansion_watch_scraper.pubsub.job_trace import JobTraceHandler

# Configure structured logging
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# Add module context to logger
logger = logging.LoggerAdapter(
    logger,
    {
        "component": "pubsub_job_trace_server",
        "operation": "server",
    },
)


def run_server():
    """Run the job trace HTTP server."""
    # Get server port from environment variable or use default
    port = int(os.getenv("JOB_TRACE_PORT", "8081"))
    server_address = ("", port)

    # Use ThreadingHTTPServer for better concurrency
    httpd = ThreadingHTTPServer(server_address, JobTraceHandler)

    logger.info(f"Starting job trace server on port {port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down server")
    finally:
        httpd.server_close()
        logger.info("Server has been shut down")


if __name__ == "__main__":
    run_server()
