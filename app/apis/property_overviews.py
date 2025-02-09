import logging
from typing import List

from fastapi import APIRouter

from app.db.session import get_db
from app.models.property_overview import PropertyOverview
from app.services.utils import to_json_serializable

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/property_overviews",
    summary="Get the property overview information",
    response_description="The property overview information",
    response_model=List[PropertyOverview],
    response_model_by_alias=False,
)
async def get_property_overview(property_id: str):
    """
    Get the property overview information.
    """
    db = get_db()
    collection = db["property_overviews"]
    found = await collection.find({"property_id": property_id}).to_list(length=100)
    property_overviews = []
    for prop in found:
        prop["_id"] = str(prop["_id"])
        property_overviews.append(to_json_serializable(prop))
    return property_overviews
