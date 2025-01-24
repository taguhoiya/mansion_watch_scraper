from fastapi import APIRouter

from app.apis.common_overviews import router as common_overview_router
from app.apis.properties import router as property_router
from app.apis.property_overviews import router as property_overview_router
from app.apis.scrape import router as scrape_router

api_router = APIRouter()
api_router.include_router(scrape_router, tags=["Scrape"], prefix="/api/v1")
api_router.include_router(property_router, tags=["Property"], prefix="/api/v1")
api_router.include_router(
    property_overview_router, tags=["Property Overview"], prefix="/api/v1"
)
api_router.include_router(
    common_overview_router, tags=["Common Overview"], prefix="/api/v1"
)
