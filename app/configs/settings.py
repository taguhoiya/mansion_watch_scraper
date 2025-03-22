import logging

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    ENV: str = "development"
    LOG_LEVEL: str
    PROJECT_NAME: str = "Mansion Watch Scraper"
    MONGO_DATABASE: str = "mansion_watch"
    MONGO_URI: str = "mongodb://localhost:27017"
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
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
