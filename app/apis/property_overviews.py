import logging
import os

from fastapi import APIRouter, HTTPException

from app.db.session import get_db
from app.services.utils import to_json_serializable

router = APIRouter()


@router.get("/property_overviews", summary="Get the property overview information")
async def get_property_overview():
    """
    Get the property overview information.
    """
    property_overviews = []
    try:
        db = get_db()
        collection_prop = db[os.getenv("COLLECTION_PROPERTY_OVERVIEWS")]
        for property_overview in await collection_prop.find().to_list(length=100):
            property_overview["_id"] = str(property_overview["_id"])
            property_overviews.append(to_json_serializable(property_overview))
    except Exception as e:
        logging.error(f"Error fetching property overviews: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    return property_overviews
