import logging
import os
from typing import List

from fastapi import APIRouter, HTTPException

from app.db.session import get_db
from app.models.common_overview import CommonOverview
from app.services.utils import to_json_serializable

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/common_overviews",
    summary="Get the common overview information",
    response_description="The common overview information",
    response_model=List[CommonOverview],
    response_model_by_alias=False,
)
async def get_common_overview(user_id: str):
    """
    Get the common overview information.
    """
    common_overviews = []
    try:
        db = get_db()
        collection_common_overviews = db[os.getenv("COLLECTION_COMMON_OVERVIEWS")]
        for common_overview in await collection_common_overviews.find(user_id).to_list(
            length=100
        ):
            common_overview["_id"] = str(common_overview["_id"])
            common_overviews.append(to_json_serializable(common_overview))
    except Exception as e:
        logging.error(f"Error fetching common overviews: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    return common_overviews
