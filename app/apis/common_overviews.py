import logging
import os

from fastapi import APIRouter, HTTPException

from app.db.session import get_db
from app.services.utils import to_json_serializable

router = APIRouter()


@router.get("/common_overviews", summary="Get the common overview information")
async def get_common_overview():
    """
    Get the common overview information.
    """
    common_overviews = []
    try:
        db = get_db()
        collection_common_overviews = db[os.getenv("COLLECTION_COMMON_OVERVIEWS")]
        for common_overview in await collection_common_overviews.find().to_list(
            length=100
        ):
            common_overview["_id"] = str(common_overview["_id"])
            common_overviews.append(to_json_serializable(common_overview))
    except Exception as e:
        logging.error(f"Error fetching common overviews: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    return common_overviews
