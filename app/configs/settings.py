import json
import logging.config
import sys

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    ENV: str = "development"
    LOG_LEVEL: str
    PROJECT_NAME: str = "Mansion Watch Scraper"
    MONGO_DATABASE: str = "mansion_watch"
    MONGODB_DATABASE: str = "mansion_watch"  # For compatibility
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGODB_URI: str = "mongodb://localhost:27017"  # For compatibility
    COLLECTION_USERS: str
    COLLECTION_USER_PROPERTIES: str
    COLLECTION_PROPERTIES: str
    COLLECTION_PROPERTY_OVERVIEWS: str
    COLLECTION_COMMON_OVERVIEWS: str
    COLLECTION_PROPERTY_IMAGES: str
    LINE_CHANNEL_SECRET: str
    LINE_CHANNEL_ACCESS_TOKEN: str
    IMAGES_STORE: str
    GOOGLE_APPLICATION_CREDENTIALS: str
    GCP_PROJECT_ID: str
    GCP_BUCKET_NAME: str
    GCP_FOLDER_NAME: str
    GCS_IMAGE_QUALITY: int
    PUBSUB_TOPIC: str = "mansion-watch-scraper-topic"
    PUBSUB_SUBSCRIPTION: str = "mansion-watch-scraper-sub-push"
    PUBSUB_MAX_MESSAGES: int = 100
    PUBSUB_MAX_BYTES: int = 10485760  # 10MB
    PUBSUB_MAX_LEASE_DURATION: int = 3600  # 1 hour
    MONGO_MAX_POOL_SIZE: int = 100
    MONGO_MIN_POOL_SIZE: int = 3
    MONGO_MAX_IDLE_TIME_MS: int = 30000
    MONGO_CONNECT_TIMEOUT_MS: int = 20000
    MONGO_WAIT_QUEUE_TIMEOUT_MS: int = 10000

    class Config:
        """Pydantic config."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "allow"  # Allow extra fields in environment variables


settings = Settings()


class StructuredLogFormatter(logging.Formatter):
    """Formatter that outputs JSON formatted logs compatible with Google Cloud Logging."""

    # Map Python logging levels to GCP severity levels
    SEVERITY_MAP = {
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "WARNING": "WARNING",
        "ERROR": "ERROR",
        "CRITICAL": "CRITICAL",
    }

    def __init__(self):
        super().__init__()
        self.project_id = settings.GCP_PROJECT_ID

    def format(self, record):
        """Format log record as JSON."""
        message = record.getMessage()
        severity = self.SEVERITY_MAP.get(record.levelname, record.levelname)

        # Basic structured log entry
        log_dict = {
            "time": self.formatTime(record),  # Add timestamp
            "severity": severity,  # Use GCP severity levels
            "message": message,  # Main display field
        }

        # Add trace and span if available
        if hasattr(record, "trace"):
            log_dict["logging.googleapis.com/trace"] = (
                f"projects/{self.project_id}/traces/{record.trace}"
            )
        if hasattr(record, "span_id"):
            log_dict["logging.googleapis.com/span_id"] = record.span_id

        # Add source location
        log_dict["logging.googleapis.com/sourceLocation"] = {
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add error info if present
        if record.exc_info:
            log_dict["@type"] = (
                "type.googleapis.com/google.devtools.clouderrorreporting.v1beta1.ReportedErrorEvent"
            )
            log_dict["error"] = self.formatException(record.exc_info)

        # Add any extra fields from the record
        if hasattr(record, "extra_fields"):
            log_dict.update(record.extra_fields)

        return json.dumps(log_dict, ensure_ascii=False)


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "()": StructuredLogFormatter,
        }
    },
    "handlers": {
        "structured": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
            "stream": sys.stdout,
        }
    },
    "loggers": {
        "": {  # Root logger
            "handlers": ["structured"],
            "level": settings.LOG_LEVEL.upper(),
            "propagate": False,
        },
        "app": {  # App logger
            "handlers": ["structured"],
            "level": settings.LOG_LEVEL.upper(),
            "propagate": False,
        },
        "app.db.monitoring": {  # Database monitoring
            "handlers": ["structured"],
            "level": "WARNING",
            "propagate": False,
        },
        "uvicorn": {  # Uvicorn server
            "handlers": ["structured"],
            "level": "WARNING",
            "propagate": False,
        },
        "motor": {  # MongoDB driver
            "handlers": ["structured"],
            "level": "WARNING",
            "propagate": False,
        },
        "pymongo": {  # MongoDB driver
            "handlers": ["structured"],
            "level": "WARNING",
            "propagate": False,
        },
        "google.cloud": {  # Google Cloud client
            "handlers": ["structured"],
            "level": "WARNING",
            "propagate": False,
        },
        "google.auth": {  # Google Auth client
            "handlers": ["structured"],
            "level": "WARNING",
            "propagate": False,
        },
        # Add Scrapy loggers to prevent redundant logs
        "scrapy": {
            "handlers": ["structured"],
            "level": "WARNING",  # Only show WARNING and above
            "propagate": False,
        },
        "scrapy.core.engine": {
            "handlers": ["structured"],
            "level": "WARNING",
            "propagate": False,
        },
        "scrapy.core.scraper": {
            "handlers": ["structured"],
            "level": "WARNING",
            "propagate": False,
        },
        "scrapy.spiders": {
            "handlers": ["structured"],
            "level": "WARNING",
            "propagate": False,
        },
        "twisted": {
            "handlers": ["structured"],
            "level": "WARNING",
            "propagate": False,
        },
        "mansion_watch_scraper.spiders.suumo_scraper": {
            "handlers": ["structured"],
            "level": "INFO",  # Keep our spider's logs but ensure they're structured
            "propagate": False,
        },
    },
}

# Initialize logging configuration
try:
    logging.config.dictConfig(LOGGING_CONFIG)
except Exception as e:
    # Fallback to basic configuration if dictConfig fails
    logging.basicConfig(level=settings.LOG_LEVEL.upper())
    logging.warning(f"Failed to configure structured logging: {e}")
