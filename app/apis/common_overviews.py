import logging
from typing import List

from bson import ObjectId
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
async def get_common_overview(property_id: str):
    """
    Get the common overview information.

    Args:
        property_id: The ID of the property to get overviews for
    """
    try:
        property_id_obj = ObjectId(property_id)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid property ID: {str(e)}",
        )

    db = get_db()
    coll = db["common_overviews"]
    found = await coll.find({"property_id": property_id_obj}).to_list(length=100)
    common_overviews = []
    for prop in found:
        prop["_id"] = str(prop["_id"])
        common_overviews.append(to_json_serializable(prop))
    return common_overviews
