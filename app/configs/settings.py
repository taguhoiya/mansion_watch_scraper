import logging

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str
    LOG_LEVEL: str
    PROJECT_NAME: str = "Mansion Watch Scraper"
    MONGO_URI: str
    MONGO_DATABASE: str
    COLLECTION_USERS: str
    COLLECTION_USER_PROPERTIES: str
    COLLECTION_PROPERTIES: str
    COLLECTION_PROPERTY_OVERVIEWS: str
    COLLECTION_COMMON_OVERVIEWS: str
    COLLECTION_PROPERTY_IMAGES: str
    LINE_CHANNEL_SECRET: str
    IMAGES_STORE: str
    GOOGLE_APPLICATION_CREDENTIALS: str
    GCP_PROJECT_ID: str
    GCP_BUCKET_NAME: str
    GCP_FOLDER_NAME: str

    class Config:
        env_file = ".env"


settings = Settings()
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
