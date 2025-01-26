from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str
    LOG_LEVEL: str
    PROJECT_NAME: str = "Mansion Watch Scraper"
    MONGO_URI: str
    MONGO_DATABASE: str
    COLLECTION_PROPERTIES: str
    COLLECTION_PROPERTY_OVERVIEWS: str
    COLLECTION_COMMON_OVERVIEWS: str


settings = Settings()
