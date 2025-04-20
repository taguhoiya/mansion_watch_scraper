"""Watchlist service module."""

import logging
import os
from typing import List, Optional

from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import (
    ConnectionFailure,
    OperationFailure,
    ServerSelectionTimeoutError,
)

from app.models.apis.watchlist import UserWatchlist
from app.models.common_overview import CommonOverview
from app.models.property_overview import PropertyOverview

logger = logging.getLogger(__name__)


class WatchlistService:
    """Service for managing user watchlists."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize the watchlist service.

        Args:
            db: The MongoDB database instance
        """
        self.db = db
        self.coll_props = db[os.getenv("COLLECTION_PROPERTIES")]
        self.coll_user_props = db[os.getenv("COLLECTION_USER_PROPERTIES")]
        self.coll_prop_ovs = db[os.getenv("COLLECTION_PROPERTY_OVERVIEWS")]
        self.coll_common_ovs = db[os.getenv("COLLECTION_COMMON_OVERVIEWS")]

    async def get_user_watchlist(self, line_user_id: str) -> List[UserWatchlist]:
        """Get the property information in the user's watchlist.

        Args:
            line_user_id: The line user id.

        Returns:
            List of properties in the user's watchlist.

        Raises:
            HTTPException: If there's an error fetching the properties.
        """
        return await self._handle_watchlist_operation(line_user_id)

    async def _handle_watchlist_operation(
        self, line_user_id: str
    ) -> List[UserWatchlist]:
        """Handle the watchlist operation with error handling.

        Args:
            line_user_id: The line user id.

        Returns:
            List of properties in the user's watchlist.

        Raises:
            HTTPException: If there's an error fetching the properties.
        """
        try:
            user_props = await self._get_user_properties(line_user_id)
            if not user_props:
                raise HTTPException(status_code=404, detail="User properties not found")

            property_ids = [prop["property_id"] for prop in user_props]
            properties = await self._get_properties(property_ids)

            # Create a mapping of property_id to property data
            property_map = {str(prop["_id"]): prop for prop in properties}

            # Maintain order from user_props while enriching properties
            ordered_properties = []
            for user_prop in user_props:
                prop_id = str(user_prop["property_id"])
                if prop_id in property_map:
                    ordered_properties.append(property_map[prop_id])

            return await self._enrich_properties(ordered_properties)

        except HTTPException:
            raise
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error("Database connection error: %s", str(e))
            raise HTTPException(
                status_code=503,
                detail="Database connection error. Please try again later.",
            )
        except OperationFailure as e:
            logger.error("Database operation error: %s", str(e))
            raise HTTPException(
                status_code=503,
                detail="Database operation error. Please try again later.",
            )
        except Exception as e:
            logger.error("Unexpected error in get_user_watchlist: %s", str(e))
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred. Please try again later.",
            )

    async def _get_user_properties(self, line_user_id: str) -> List[dict]:
        """Get user properties with retries.

        Args:
            line_user_id: The line user id.

        Returns:
            List of user properties.

        Raises:
            HTTPException: If there's an error fetching the properties.
        """
        try:
            return (
                await self.coll_user_props.find({"line_user_id": line_user_id})
                .sort("first_succeeded_at", -1)
                .to_list(length=None)
            )
        except Exception as e:
            logger.error("Error fetching user properties: %s", str(e))
            raise

    async def _get_properties(self, property_ids: List[ObjectId]) -> List[dict]:
        """Get properties with retries.

        Args:
            property_ids: List of property IDs.

        Returns:
            List of properties.

        Raises:
            HTTPException: If there's an error fetching the properties.
        """
        try:
            return await self.coll_props.find({"_id": {"$in": property_ids}}).to_list(
                length=None
            )
        except Exception as e:
            logger.error("Error fetching properties: %s", str(e))
            raise

    async def _enrich_properties(self, properties: List[dict]) -> List[UserWatchlist]:
        """Enrich multiple properties with additional information.

        Args:
            properties: List of base property information.

        Returns:
            List of enriched properties.
        """
        enriched_properties = []
        for prop in properties:
            try:
                prop_id = prop["_id"]
                enriched_prop = await self._enrich_property(prop_id, prop)
                if enriched_prop:
                    enriched_properties.append(enriched_prop)
            except Exception as e:
                logger.error(
                    "Error enriching property %s: %s",
                    prop_id,
                    str(e),
                )
        return enriched_properties

    async def _enrich_property(
        self, prop_id: ObjectId, prop: dict
    ) -> Optional[UserWatchlist]:
        """Enrich a property with overview information.

        Args:
            prop_id: The property ID
            prop: The base property information

        Returns:
            The enriched property information
        """
        # Set default values for required fields if they don't exist
        defaults = {
            "is_active": True,
            "price": "情報なし",
            "floor_plan": "情報なし",
            "completion_time": "情報なし",
            "area": "情報なし",
            "other_area": "情報なし",
            "location": "情報なし",
            "transportation": ["情報なし"],
        }

        # Only update missing fields with defaults
        for key, value in defaults.items():
            if key not in prop:
                prop[key] = value

        try:
            # Add property overview information if available
            prop_ov = await self._get_property_overview(prop_id)
            if prop_ov:
                prop.update(
                    {
                        "price": prop_ov["price"],
                        "floor_plan": prop_ov["floor_plan"],
                        "completion_time": prop_ov["completion_time"],
                        "area": prop_ov["area"],
                        "other_area": prop_ov["other_area"],
                    }
                )
            else:
                logger.warning(
                    "Property overview not found for property %s, using defaults",
                    prop_id,
                )

            # Add common overview information if available
            common_ov = await self._get_common_overview(prop_id)
            if common_ov:
                prop.update(
                    {
                        "location": common_ov["location"],
                        "transportation": common_ov["transportation"],
                    }
                )
            else:
                logger.warning(
                    "Common overview not found for property %s, using defaults",
                    prop_id,
                )

            # Only keep the first image URL if available
            if "image_urls" in prop and prop["image_urls"]:
                prop["image_urls"] = [prop["image_urls"][0]]
            else:
                prop["image_urls"] = []

            return UserWatchlist(**prop)

        except Exception as e:
            logger.error(
                "Failed to enrich property %s: %s",
                prop_id,
                str(e),
            )
            return None

    async def _get_property_overview(
        self, prop_id: ObjectId
    ) -> Optional[PropertyOverview]:
        """Get property overview information with error handling."""
        try:
            prop_ovs = await self.coll_prop_ovs.find({"property_id": prop_id}).to_list(
                length=1
            )
            return prop_ovs[0] if prop_ovs else None
        except Exception as e:
            logger.error("Error fetching property overview: %s", str(e))
            return None

    async def _get_common_overview(self, prop_id: ObjectId) -> Optional[CommonOverview]:
        """Get common overview information with error handling."""
        try:
            common_ovs = await self.coll_common_ovs.find(
                {"property_id": prop_id}
            ).to_list(length=1)
            return common_ovs[0] if common_ovs else None
        except Exception as e:
            logger.error("Error fetching common overview: %s", str(e))
            return None
