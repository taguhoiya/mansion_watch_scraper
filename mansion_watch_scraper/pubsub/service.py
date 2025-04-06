import base64
import json
import logging
import multiprocessing
import os
import signal
import sys
from datetime import datetime
from logging import LoggerAdapter
from threading import Lock
from typing import Any, Dict, Optional, Union

from dotenv import load_dotenv
from google.cloud import pubsub_v1
from pydantic import BaseModel, field_validator
from scrapy import signals
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from app.configs.settings import LOGGING_CONFIG
from mansion_watch_scraper.spiders.suumo_scraper import MansionWatchSpider

# Set multiprocessing start method to 'spawn' to avoid gRPC fork issues
if sys.platform != "win32":  # Not needed on Windows as it uses spawn by default
    multiprocessing.set_start_method("spawn", force=True)

load_dotenv()

# Get logger for this module
logger = logging.getLogger(__name__)

# Configure structured logging
logger = LoggerAdapter(
    logger,
    {
        "component": "pubsub_service",
        "operation": "message_processing",  # Default operation for this service
    },
)

# Check if using local emulator
PUBSUB_EMULATOR_HOST = os.getenv("PUBSUB_EMULATOR_HOST")
if PUBSUB_EMULATOR_HOST:
    logger.info(
        f"Using Pub/Sub emulator at {PUBSUB_EMULATOR_HOST}",
        extra={"operation": "service_init"},
    )
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = ""  # Not needed for emulator


def configure_logging():
    """Configure logging for the service."""
    # Use the structured logging configuration from settings
    logging.config.dictConfig(LOGGING_CONFIG)

    # Configure all other loggers to WARNING and prevent propagation
    for logger_name in [
        "scrapy",
        "twisted",
        "asyncio",
        "urllib3",
        "google.cloud",
        "google.auth",
        "pymongo",
        "pymongo.topology",
        "botocore",
        "boto3",
        "s3transfer",
        "filelock",
        "PIL",
        "absl",
        "grpc",
        "charset_normalizer",
        "parso",
        "jedi",
        "httpx",
        "httpcore",
        "aiohttp",
        "requests",
        "matplotlib",
        "selenium",
        "scrapy.core.engine",
        "scrapy.core.scraper",
        "scrapy.statscollectors",
        "scrapy.middleware",
        "scrapy.extensions",
        "scrapy.utils.log",
        "scrapy.logformatter",
        "scrapy.core.downloader",
        "scrapy.spidermiddlewares",
        "scrapy.downloadermiddlewares",
        "scrapy.extensions.telnet",
        "scrapy.extensions.logstats",
        "scrapy.extensions.memusage",
        "scrapy.extensions.corestats",
        "scrapy.extensions.closespider",
        "scrapy.pipelines",
        "scrapy.dupefilters",
        "scrapy.crawler",
        "scrapy.settings",
        "scrapy.signals",
        "scrapy.utils.project",
        "scrapy.utils.conf",
        "scrapy.utils.misc",
        "scrapy.utils.log",
        "scrapy.utils.ossignal",
        "scrapy.utils.reactor",
        "scrapy.utils.reqser",
        "scrapy.utils.serialize",
        "scrapy.utils.signal",
        "scrapy.utils.spider",
        "scrapy.utils.trackref",
        "scrapy.utils.url",
        "scrapy.utils.versions",
        "twisted.internet.asyncioreactor",
        "twisted.internet",
        "asyncio.unix_events",
        "mansion_watch_scraper.pipelines",  # Add this to control pipeline logs
    ]:
        log = logging.getLogger(logger_name)
        log.setLevel(logging.WARNING)
        log.propagate = False  # Prevent propagation to root logger

    # Set root logger to INFO to exclude DEBUG logs
    logging.getLogger().setLevel(logging.INFO)


class MessageData(BaseModel):
    """Model for message data."""

    timestamp: datetime
    url: str
    line_user_id: str
    check_only: bool = False

    @field_validator("line_user_id")
    def validate_line_user_id(cls, v):
        """Validate that line_user_id starts with 'U'."""
        if not v.startswith("U"):
            raise ValueError("line_user_id must start with U")
        return v

    class Config:
        extra = "ignore"  # Ignore extra fields in the input data


class PubSubService:
    """Service for handling Pub/Sub messages."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self, project_id: Optional[str] = None, subscription_name: Optional[str] = None
    ):
        """Initialize the service."""
        if not self._initialized:
            # Configure logging first
            configure_logging()

            self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
            if not self.project_id:
                raise ValueError("GCP_PROJECT_ID environment variable is not set")

            self.subscription_name = subscription_name or os.getenv(
                "PUBSUB_SUBSCRIPTION", "mansion-watch-scraper-sub-pull"
            )

            self.flow_control = pubsub_v1.types.FlowControl(
                max_messages=10,  # Maximum number of messages to hold in memory
                max_bytes=50
                * 1024
                * 1024,  # Maximum size of messages to hold in memory (50MB)
                max_lease_duration=600,  # Maximum number of seconds to hold messages before releasing
            )

            self.subscriber = None
            self.is_running = False
            self._processed_messages = set()
            self._lock = Lock()  # Add lock for thread safety
            self._settings = get_project_settings()

            # Skip service account check if using emulator
            if not os.getenv("PUBSUB_EMULATOR_HOST"):
                # Set credentials path
                service_account_paths = [
                    "/app/secrets/service-account.json",
                    "/app/service-account.json",
                    "service-account.json",
                ]

                creds_path = next(
                    (path for path in service_account_paths if os.path.exists(path)),
                    None,
                )
                if not creds_path:
                    raise FileNotFoundError(
                        f"Service account file not found in any of: {', '.join(service_account_paths)}"
                    )

                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path

            self._initialized = True

    def run_spider(
        self, url: str, line_user_id: str, check_only: bool = False
    ) -> Dict[str, Any]:
        """Run the spider in a separate process and return its results."""
        queue = multiprocessing.Queue()
        process = multiprocessing.Process(
            target=_run_spider_process, args=(url, line_user_id, check_only, queue)
        )

        try:
            process.start()
            process.join(
                timeout=300
            )  # Wait up to 300 seconds for the spider to complete

            if process.is_alive():
                process.terminate()
                process.join()
                return {
                    "type": "result",
                    "status": "error",
                    "error_type": "TimeoutError",
                    "error_message": "Spider execution timed out after 300 seconds",
                    "url": url,
                }

            results = {}
            # Process all messages from the queue
            while not queue.empty():
                msg = queue.get()
                if msg.get("type") == "result":
                    # Remove the type field and use the rest as results
                    results = {k: v for k, v in msg.items() if k != "type"}
                elif msg.get("log"):
                    # Handle log messages from the spider process
                    level = msg["log"]
                    message = msg["message"]
                    if hasattr(logger, level):
                        getattr(logger, level)(message)

            if results:
                return results

            return {
                "type": "result",
                "status": "error",
                "error_type": "ProcessError",
                "error_message": "Spider process ended without returning results",
                "url": url,
            }

        except Exception as e:
            if process.is_alive():
                process.terminate()
                process.join()
            return {
                "type": "result",
                "status": "error",
                "error_type": e.__class__.__name__,
                "error_message": str(e),
                "url": url,
            }

    def _extract_message_data(
        self, message: Union[pubsub_v1.subscriber.message.Message, Dict[str, Any]]
    ) -> tuple[str, bytes]:
        """Extract message ID and data from a message."""
        if isinstance(message, dict):
            message_id = message.get("messageId", "unknown")
            try:
                data = (
                    base64.b64decode(message.get("data", ""))
                    if message.get("data")
                    else b""
                )
            except Exception as e:
                logger.error(f"Failed to decode base64 message data: {e}")
                raise
        else:
            message_id = message.message_id
            data = message.data
        return message_id, data

    def _handle_spider_results(self, results: Dict[str, Any], url: str) -> None:
        """Handle and log spider execution results."""
        status = results.get("status", "unknown")
        if status in ["error", "not_found"]:
            if status == "not_found":
                logger.error("Property not found (404)")
            else:
                logger.error(f"Error type: {results.get('error_type')}")
                logger.error(f"Error message: {results.get('error_message')}")
        elif status == "success":
            property_info = results.get("property_info", {})
            processing_status = results.get("status", "unknown")
            property_name = property_info.get("properties", {}).get("name", "unknown")

            if processing_status == "stored":
                logger.info(f"Successfully stored property: {property_name} ({url})")
            else:
                logger.info(f"Successfully checked property: {property_name} ({url})")
        else:
            logger.warning(f"Unknown status '{status}' for URL: {url}")

    def message_callback(
        self, message: Union[pubsub_v1.subscriber.message.Message, Dict[str, Any]]
    ) -> None:
        """Process a Pub/Sub message."""
        try:
            with self._lock:  # Use lock when processing messages
                # Decode message data
                if "data" not in message:
                    logger.error(
                        "No data field in message",
                        extra={"operation": "message_validation"},
                    )
                    return

                message_id, data = self._extract_message_data(message)
                logger.info(
                    f"Received message with ID: {message_id}",
                    extra={"operation": "message_received", "message_id": message_id},
                )

                if message_id in self._processed_messages:
                    logger.info(
                        f"Message {message_id} already processed, skipping",
                        extra={
                            "operation": "message_deduplication",
                            "message_id": message_id,
                        },
                    )
                    return

                self._processed_messages.add(message_id)
                if len(self._processed_messages) > 1000:
                    self._processed_messages.clear()

                try:
                    data_str = data.decode("utf-8") if isinstance(data, bytes) else data
                    data_dict = json.loads(data_str)
                    message_data = MessageData(**data_dict)
                except Exception as e:
                    logger.error(f"Failed to parse message data: {e}")
                    return

                logger.info(
                    f"Running spider for URL: {message_data.url}",
                    extra={
                        "operation": "spider_start",
                        "message_id": message_id,
                        "url": message_data.url,
                        "line_user_id": message_data.line_user_id,
                    },
                )
                results = self.run_spider(
                    url=message_data.url,
                    line_user_id=message_data.line_user_id,
                    check_only=message_data.check_only,
                )

                self._handle_spider_results(results, message_data.url)
                logger.info("Listening for messages...")

        except Exception as e:
            logger.error(
                "Error processing message",
                extra={
                    "operation": "message_error",
                    "message_id": message_id,
                    "error": str(e),
                    "error_type": e.__class__.__name__,
                },
                exc_info=True,
            )
            logger.info("Listening for messages...")
            raise

    def start(self) -> None:
        """Start the Pub/Sub subscriber."""
        if self.is_running:
            logger.warning("Service is already running")
            return

        try:
            # Create subscriber client
            subscriber = pubsub_v1.SubscriberClient()
            subscription_path = subscriber.subscription_path(
                self.project_id, self.subscription_name
            )

            # Subscribe to the topic
            self.subscriber = subscriber.subscribe(
                subscription_path,
                callback=self.message_callback,
                flow_control=self.flow_control,
            )

            self.is_running = True

            # Log environment variables and startup message
            logger.info("Environment variables:")
            logger.info(f"GCP_PROJECT_ID: {self.project_id}")
            logger.info(f"PUBSUB_SUBSCRIPTION: {self.subscription_name}")
            logger.info(f"GCP_BUCKET_NAME: {os.getenv('GCP_BUCKET_NAME', 'Not set')}")
            logger.info(f"GCP_FOLDER_NAME: {os.getenv('GCP_FOLDER_NAME', 'Not set')}")
            logger.info(f"IMAGES_STORE: {os.getenv('IMAGES_STORE', 'Not set')}")
            logger.info("Starting service...")
            logger.info("Listening for messages...")

            # Keep the main thread from exiting
            self.subscriber.result()

        except Exception as e:
            logger.error(f"Error starting service: {e}")
            self.stop()
            sys.exit(1)

    def stop(self) -> None:
        """Stop the Pub/Sub subscriber."""
        if not self.is_running:
            return

        try:
            if self.subscriber:
                self.subscriber.cancel()
                self.subscriber = None
            self.is_running = False
            logger.info("Service stopped")
        except Exception as e:
            logger.error(f"Error stopping service: {e}")


def _run_spider_process(
    url: str, line_user_id: str, check_only: bool, queue: multiprocessing.Queue
) -> None:
    """Run the spider in a separate process."""
    try:
        # Initialize settings
        settings = get_project_settings()

        # Configure spider process settings
        settings.setdict(
            {
                "ROBOTSTXT_OBEY": False,
                "COOKIES_ENABLED": False,
                "DOWNLOAD_TIMEOUT": 30,
                "CONCURRENT_REQUESTS": 1,
                "DOWNLOAD_DELAY": 0,
                "CLOSESPIDER_PAGECOUNT": 1,
                # Enable minimal logging for spider process
                "LOG_ENABLED": True,
                "LOG_LEVEL": "INFO",
                "LOG_STDOUT": True,
                "LOG_FILE": None,
                # Configure log format to match service
                "LOG_FORMAT": "%(asctime)s %(levelname)s: %(message)s",
                "LOG_DATEFORMAT": "%Y-%m-%d %H:%M:%S",
                # Disable unnecessary logs
                "LOG_STATS": False,
                "LOG_DUPEFILTER": False,
                "STATS_DUMP": False,
                # Disable unnecessary extensions
                "EXTENSIONS": {
                    "scrapy.extensions.logstats.LogStats": None,
                    "scrapy.extensions.corestats.CoreStats": None,
                    "scrapy.extensions.memusage.MemoryUsage": None,
                    "scrapy.extensions.feedexport.FeedExporter": None,
                    "scrapy.extensions.telnet.TelnetConsole": None,
                },
                "TELNETCONSOLE_ENABLED": False,
                # Disable feed exports
                "FEED_EXPORT_ENABLED": False,
                "FEED_STORAGES": {},
                "FEED_EXPORTERS": {},
                "FEED_EXPORT_BATCH_ITEM_COUNT": 0,
                # MongoDB settings
                "MONGO_URI": os.getenv("MONGO_URI"),
                "MONGO_DATABASE": os.getenv("MONGO_DATABASE"),
                # GCS settings
                "GCP_PROJECT_ID": os.getenv("GCP_PROJECT_ID"),
                "GCP_BUCKET_NAME": os.getenv("GCP_BUCKET_NAME"),
                "GCP_FOLDER_NAME": os.getenv("GCP_FOLDER_NAME"),
                "IMAGES_STORE": os.getenv("IMAGES_STORE"),
            },
            priority="cmdline",
        )

        # Configure pipelines based on check_only mode
        if check_only:
            settings.set("ITEM_PIPELINES", {}, priority="cmdline")
            queue.put(
                {
                    "log": "info",
                    "message": "Running in check-only mode (pipelines disabled)",
                }
            )
        else:
            settings.set(
                "ITEM_PIPELINES",
                {
                    "mansion_watch_scraper.pipelines.MongoPipeline": 300,
                    "mansion_watch_scraper.pipelines.SuumoImagesPipeline": 1,
                },
                priority="cmdline",
            )

        # Configure logging for specific components
        configure_logging()

        results = {}
        scraped_items = []

        def handle_item_scraped(item, response, spider):
            scraped_items.append(item)

        def handle_spider_closed(spider, reason):
            nonlocal results
            # Get the results from the spider
            spider_results = getattr(spider, "results", {})

            # Check if we have scraped items
            if scraped_items:
                results = {
                    "status": "success",
                    "property_info": scraped_items[0],
                    "processing_status": "stored" if not check_only else "checked",
                }
            # If we have a 404 status from spider results
            elif spider_results.get("status_code") == 404:
                results = {
                    "status": "not_found",
                    "error_type": "HttpError",
                    "error_message": "Property not found (404). The URL may be incorrect or the property listing may have been removed.",
                    "url": url,
                }
            # If we have other results from the spider
            elif spider_results:
                results = spider_results
            else:
                results = {
                    "status": "error",
                    "error_type": "SpiderError",
                    "error_message": f"Spider completed with reason: {reason}, but no results were returned",
                    "url": url,
                }

        # Create the crawler process with configured settings
        process = CrawlerProcess(settings)

        # Configure spider settings
        spider_kwargs = {
            "url": url,
            "line_user_id": line_user_id,
            "check_only": check_only,
        }

        # Connect signals before crawling
        crawler = process.create_crawler(MansionWatchSpider)
        crawler.signals.connect(handle_spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(handle_item_scraped, signal=signals.item_scraped)

        # Add the spider to crawl
        process.crawl(crawler, **spider_kwargs)

        # Start the crawl and block until finished
        process.start()

        # Put the results in the queue
        queue.put({"type": "result", **results})

    except Exception as e:
        queue.put(
            {
                "type": "result",
                "status": "error",
                "error_type": e.__class__.__name__,
                "error_message": str(e),
                "url": url,
            }
        )


def main() -> None:
    """Main function to start the service."""
    service = None

    def handle_shutdown(signum, frame):
        logger.info(f"Received signal {signum}")
        if service:
            logger.info("Shutting down gracefully...")
            service.stop()
        sys.exit(0)

    try:
        # Set up signal handlers
        signal.signal(signal.SIGTERM, handle_shutdown)
        signal.signal(signal.SIGINT, handle_shutdown)

        service = PubSubService()
        service.start()

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        if service:
            service.stop()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        if service:
            service.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
