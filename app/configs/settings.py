import logging

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
    PUBSUB_TOPIC: str = "mansion-watch-scraper"
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


settings = Settings()

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(levelname)s:%(name)s:%(message)s"},
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "": {
            "handlers": ["default"],
            "level": "INFO",
        },
        "app.db.monitoring": {
            "handlers": ["default"],
            "level": "WARNING",
            "propagate": False,
        },
        "motor": {"handlers": ["default"], "level": "WARNING", "propagate": False},
        "pymongo": {"handlers": ["default"], "level": "WARNING", "propagate": False},
    },
}

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
