from fastapi import APIRouter

from app.apis.scrape import router as scrape_router

api_router = APIRouter()
api_router.include_router(
    scrape_router, tags=["Scrape a target apartment URL"], prefix="/api/v1"
)
