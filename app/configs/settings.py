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
    LINE_CHANNEL_SECRET: str

    class Config:
        env_file = ".env"


settings = Settings()
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
