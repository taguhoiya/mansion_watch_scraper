import logging
import os

from fastapi import APIRouter, HTTPException

from app.db.session import get_db
from app.services.utils import to_json_serializable

router = APIRouter()


@router.get("/properties", summary="Get the property information")
async def get_property():
    """
    Get the property information.
    """
    properties = []
    try:
        db = get_db()
        collection_prop = db[os.getenv("COLLECTION_PROPERTY_OVERVIEWS")]
        for property in await collection_prop.find().to_list(length=100):
            print(property)
            property["_id"] = str(property["_id"])
            properties.append(to_json_serializable(property))
    except Exception as e:
        logging.error(f"Error fetching properties: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    return properties
