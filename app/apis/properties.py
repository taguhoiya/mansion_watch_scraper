import logging
import os
from typing import List

from fastapi import APIRouter, HTTPException

from app.db.session import get_db
from app.models.property import Property
from app.services.utils import to_json_serializable

router = APIRouter()
logger = logging.getLogger(__name__)


async def _get_properties_by_user_and_url(
    line_user_id: str, url: str, collection_user_prop, collection_prop
) -> list:
    props = []
    user_properties = await collection_user_prop.find(
        {"line_user_id": line_user_id}
    ).to_list(length=100)
    for user_property in user_properties:
        found = await collection_prop.find(
            {"_id": user_property["property_id"], "url": url}
        ).to_list(length=100)
        for prop in found:
            prop["_id"] = str(prop["_id"])
            props.append(to_json_serializable(prop))
    return props


async def _get_properties_by_user(
    line_user_id: str, collection_user_prop, collection_prop
) -> list:
    props = []
    user_properties = await collection_user_prop.find(
        {"line_user_id": line_user_id}
    ).to_list(length=100)
    for user_property in user_properties:
        found = await collection_prop.find(
            {"_id": user_property["property_id"]}
        ).to_list(length=100)
        for prop in found:
            prop["_id"] = str(prop["_id"])
            props.append(to_json_serializable(prop))
    return props


async def _get_properties_by_url(url: str, collection_prop) -> list:
    props = []
    found = await collection_prop.find({"url": url}).to_list(length=100)
    for prop in found:
        prop["_id"] = str(prop["_id"])
        props.append(to_json_serializable(prop))
    return props


@router.get(
    "/properties",
    summary="Get the property information",
    response_description="The property information",
    response_model=List[Property],
    response_model_by_alias=False,
)
async def get_property(url: str = None, line_user_id: str = None):
    """
    Get the property information.
    Either url or line_user_id must be provided.
    """
    if not url and not line_user_id:
        raise HTTPException(
            status_code=400, detail="Either url or line_user_id must be provided"
        )

    try:
        db = get_db()
        collection_prop = db[os.getenv("COLLECTION_PROPERTIES")]
        collection_user_prop = db[os.getenv("COLLECTION_USER_PROPERTIES")]

        if line_user_id and url:
            properties = await _get_properties_by_user_and_url(
                line_user_id, url, collection_user_prop, collection_prop
            )
        elif line_user_id:
            properties = await _get_properties_by_user(
                line_user_id, collection_user_prop, collection_prop
            )
        elif url:
            properties = await _get_properties_by_url(url, collection_prop)
        else:
            properties = []
    except Exception as e:
        logger.error(f"Error fetching properties: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    return properties
