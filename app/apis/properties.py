import logging
import os
from typing import List

from fastapi import APIRouter, HTTPException

from app.db.session import get_db
from app.models.property import Property
from app.services.utils import to_json_serializable

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/properties",
    summary="Get the property information",
    response_description="The property information",
    response_model=List[Property],
    response_model_by_alias=False,
)
async def get_property():
    """
    Get the property information.
    """
    properties = []
    try:
        db = get_db()
        collection_prop = db[os.getenv("COLLECTION_PROPERTIES")]
        for property in await collection_prop.find().to_list(length=100):
            property["_id"] = str(property["_id"])
            properties.append(to_json_serializable(property))
    except Exception as e:
        logging.error(f"Error fetching properties: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    return properties
