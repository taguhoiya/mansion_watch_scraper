from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str
    PROJECT_NAME: str = "Mansion Watch Scraper"
    MONGO_URI: str
    MONGO_DATABASE: str
    TABLE_PROPERTIES: str
    TABLE_PROPERTIES_OVERVIEW: str
    TABLE_COMMON_OVERVIEW: str


settings = Settings()
