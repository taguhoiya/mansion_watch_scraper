"""API router module."""

from fastapi import APIRouter

from app.apis.common_overviews import router as common_overviews_router
from app.apis.messages import router as messages_router
from app.apis.property_overviews import router as property_overviews_router
from app.apis.scrape import router as scrape_router
from app.apis.users import router as users_router
from app.apis.webhooks import router as webhooks_router

api_router = APIRouter()

# Include routers from each API module
api_router.include_router(scrape_router, prefix="/scrape", tags=["Scrape"])
api_router.include_router(messages_router, prefix="/messages", tags=["Messages"])
api_router.include_router(users_router, prefix="/users", tags=["Users"])
api_router.include_router(webhooks_router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(
    property_overviews_router, prefix="/property-overviews", tags=["Property Overviews"]
)
api_router.include_router(
    common_overviews_router, prefix="/common-overviews", tags=["Common Overviews"]
)
