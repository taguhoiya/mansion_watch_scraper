from fastapi import APIRouter

from app.apis.common_overviews import router as common_overview_router
from app.apis.job_trace import router as job_trace_router
from app.apis.property_overviews import router as property_overview_router
from app.apis.scrape import router as scrape_router
from app.apis.users import router as users_router
from app.apis.webhooks import router as webhooks_router

api_router = APIRouter()
api_router.include_router(scrape_router, tags=["Scrape"], prefix="/api/v1")
api_router.include_router(
    property_overview_router, tags=["Property Overview"], prefix="/api/v1"
)
api_router.include_router(
    common_overview_router, tags=["Common Overview"], prefix="/api/v1"
)
api_router.include_router(webhooks_router, tags=["Webhooks"], prefix="/api/v1")
api_router.include_router(users_router, tags=["Users"], prefix="/api/v1")
api_router.include_router(job_trace_router, tags=["Job Traces"], prefix="/api/v1/jobs")
