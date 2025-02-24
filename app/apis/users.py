import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.session import get_db
from app.models.apis.watchlist import UserWatchlist
from app.services.watchlist_service import WatchlistService

router = APIRouter()
logger = logging.getLogger(__name__)


async def get_watchlist_service(
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> WatchlistService:
    return WatchlistService(db)


@router.get(
    "/users/{line_user_id}/watchlist",
    summary="Get the property information in the watchlist",
    response_description="The property information in the watchlist",
    response_model=List[UserWatchlist],
    response_model_by_alias=False,
)
async def get_property_watchlist(
    line_user_id: str,
    url: str | None = None,
    service: WatchlistService = Depends(get_watchlist_service),
) -> List[UserWatchlist]:
    """
    Get the property information in the watchlist.

    Args:
        line_user_id (str): The line user id.
        url (str, optional): The url.
        service (WatchlistService): The watchlist service dependency.

    Returns:
        List[UserWatchlist]: The property information in the user's watchlist.

    Raises:
        HTTPException: If there's an error fetching the properties.
    """
    try:
        return await service.get_user_watchlist(line_user_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error fetching properties for user {line_user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
