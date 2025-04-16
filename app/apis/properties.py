import logging
import os
from typing import Dict, List, Union

from bson import ObjectId
from fastapi import APIRouter, HTTPException

from app.db.session import get_db
from app.models.common_overview import CommonOverview
from app.models.property import Property
from app.models.property_overview import PropertyOverview
from app.services.utils import to_json_serializable

router = APIRouter()
logger = logging.getLogger(__name__)
collection_properties = os.getenv("COLLECTION_PROPERTIES")
collection_user_properties = os.getenv("COLLECTION_USER_PROPERTIES")
collection_property_overviews = os.getenv("COLLECTION_PROPERTY_OVERVIEWS")
collection_common_overviews = os.getenv("COLLECTION_COMMON_OVERVIEWS")


async def _get_properties_by_user_and_url(
    line_user_id: str, url: str, coll_user_prop, coll_prop
) -> list:
    props = []
    user_properties = await coll_user_prop.find({"line_user_id": line_user_id}).to_list(
        length=100
    )
    for user_property in user_properties:
        found = await coll_prop.find(
            {"_id": user_property["property_id"], "url": url}
        ).to_list(length=100)
        for prop in found:
            prop["_id"] = str(prop["_id"])
            props.append(to_json_serializable(prop))
    return props


async def _get_properties_by_user(
    line_user_id: str, coll_user_prop, coll_prop
) -> List[Property]:
    props = []
    user_properties = await coll_user_prop.find({"line_user_id": line_user_id}).to_list(
        length=100
    )
    for user_property in user_properties:
        found = await coll_prop.find({"_id": user_property["property_id"]}).to_list(
            length=100
        )
        for prop in found:
            prop["_id"] = str(prop["_id"])
            props.append(to_json_serializable(prop))
    return props


async def _get_properties_by_url(url: str, coll_prop) -> list:
    props = []
    found = await coll_prop.find({"url": url}).to_list(length=100)
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
    # Guard clause for required parameters
    if not url and not line_user_id:
        raise HTTPException(
            status_code=400,
            detail="Either url or line_user_id must be provided",
        )

    try:
        db = get_db()
        coll_prop = db[collection_properties]
        coll_user_prop = db[collection_user_properties]

        if line_user_id and url:
            properties = await _get_properties_by_user_and_url(
                line_user_id, url, coll_user_prop, coll_prop
            )
        elif line_user_id:
            properties = await _get_properties_by_user(
                line_user_id, coll_user_prop, coll_prop
            )
        else:
            properties = await _get_properties_by_url(url, coll_prop)

        if not properties:
            raise HTTPException(
                status_code=404,
                detail="Property not found",
            )

        return properties

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error fetching properties: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while fetching properties",
        )


@router.get(
    "/properties/{property_id}",
    summary="Get the property information by property id",
    response_description="The property information",
    response_model=Dict[str, Union[Property, PropertyOverview, CommonOverview]],
    response_model_by_alias=False,
)
async def get_property_by_id(property_id: str):
    """Get the property information by property id."""
    try:
        # Validate ObjectId format first
        if not ObjectId.is_valid(property_id):
            raise HTTPException(
                status_code=400,
                detail="Invalid property_id format. Must be a 24-character hex string",
            )

        obj_id = ObjectId(property_id)
        db = get_db()
        coll_prop = db[collection_properties]
        coll_prop_ov = db[collection_property_overviews]
        coll_prop_common_ov = db[collection_common_overviews]

        # Query with ObjectId but convert to string in response
        prop: Property = await coll_prop.find_one({"_id": obj_id})
        if not prop:
            raise HTTPException(status_code=404, detail="Property not found")

        prop_ov: PropertyOverview = await coll_prop_ov.find_one({"property_id": obj_id})
        if not prop_ov:
            raise HTTPException(status_code=404, detail="Property overview not found")

        common_ov: CommonOverview = await coll_prop_common_ov.find_one(
            {"property_id": obj_id}
        )
        if not common_ov:
            raise HTTPException(status_code=404, detail="Common overview not found")

        # Convert all ObjectIds to strings and preserve all fields
        result = {
            "property": to_json_serializable(prop),
            "property_overview": to_json_serializable(prop_ov),
            "common_overview": to_json_serializable(common_ov),
        }

        return result

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error fetching property: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
