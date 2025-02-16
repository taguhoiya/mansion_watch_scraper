import logging
import os
from typing import List

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from app.apis.properties import _get_properties_by_user
from app.db.session import get_db
from app.models.common_overview import CommonOverview
from app.models.property import Property
from app.models.property_image import PropertyImage
from app.models.property_overview import PropertyOverview

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/users/{line_user_id}/watchlist",
    summary="Get the property information in the watchlist",
    response_description="The property information in the watchlist",
    # response_model=List[Property],
    response_model_by_alias=False,
)
async def get_property_watchlist(line_user_id: str = None, url: str = None):
    """
    Get the property information in the watchlist.

    Args:
        line_user_id (str): The line user id.
        url (str): The url.

    Returns:
        list: The property information in the user's watchlist.
    """
    try:
        db = get_db()
        coll_props = db[os.getenv("COLLECTION_PROPERTIES")]
        coll_user_props = db[os.getenv("COLLECTION_USER_PROPERTIES")]
        coll_prop_ovs = db[os.getenv("COLLECTION_PROPERTY_OVERVIEWS")]
        coll_common_ovs = db[os.getenv("COLLECTION_COMMON_OVERVIEWS")]

        properties: List[Property] = await _get_properties_by_user(
            line_user_id, coll_user_props, coll_props
        )

        images = AsyncIOMotorGridFSBucket(db, os.getenv("COLLECTION_PROPERTY_IMAGES"))

        for prop in properties:
            prop_id = prop["_id"]
            prop["is_active"] = True

            images_list: List[PropertyImage] = await images.find(
                {"metadata.url": prop["url"]}
            ).to_list(length=100)

            prop_ovs: List[PropertyOverview] = await coll_prop_ovs.find(
                {"property_id": ObjectId(prop_id)}
            ).to_list(length=100)
            if prop_ovs:
                prop_ov = prop_ovs[0]
                prop["price"] = prop_ov["price"]
                prop["floor_plan"] = prop_ov["floor_plan"]
                prop["completion_time"] = prop_ov["completion_time"]
                prop["area"] = prop_ov["area"]
                prop["other_area"] = prop_ov["other_area"]
            common_ovs: List[CommonOverview] = await coll_common_ovs.find(
                {"property_id": ObjectId(prop_id)}
            ).to_list(length=100)
            if common_ovs:
                common_ov = common_ovs[0]
                prop["location"] = common_ov["location"]
                prop["transportation"] = common_ov["transportation"]
            if images_list:
                for image in images_list:
                    image["_id"] = str(image["_id"])
                prop["images"] = images_list

    except Exception as e:
        logger.error(f"Error fetching properties: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    return properties
