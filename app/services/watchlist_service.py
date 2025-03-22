import logging
import os
from typing import List

from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.apis.watchlist import UserWatchlist
from app.models.common_overview import CommonOverview
from app.models.property_overview import PropertyOverview

logger = logging.getLogger(__name__)


class WatchlistService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.coll_props = db[os.getenv("COLLECTION_PROPERTIES")]
        self.coll_user_props = db[os.getenv("COLLECTION_USER_PROPERTIES")]
        self.coll_prop_ovs = db[os.getenv("COLLECTION_PROPERTY_OVERVIEWS")]
        self.coll_common_ovs = db[os.getenv("COLLECTION_COMMON_OVERVIEWS")]

    async def get_user_watchlist(self, line_user_id: str) -> List[UserWatchlist]:
        """
        Get the property information in the user's watchlist.

        Args:
            line_user_id (str): The line user id.

        Returns:
            List[UserWatchlist]: List of properties in the user's watchlist.
        """
        # Get base properties
        user_props = await self.coll_user_props.find(
            {"line_user_id": line_user_id}
        ).to_list(length=None)

        if not user_props:
            raise HTTPException(status_code=404, detail="User properties not found")

        property_ids = [prop["property_id"] for prop in user_props]
        properties = await self.coll_props.find({"_id": {"$in": property_ids}}).to_list(
            length=None
        )

        # Enrich properties with additional information
        enriched_properties = []
        for prop in properties:
            try:
                prop_id = prop["_id"]
                enriched_prop = await self._enrich_property(prop_id, prop)
                if enriched_prop:
                    enriched_properties.append(enriched_prop)
            except Exception as e:
                # Log the error but continue processing other properties
                logger.error(
                    "Error enriching property %s: %s",
                    prop_id,
                    str(e),
                )

        return enriched_properties

    async def _enrich_property(
        self, prop_id: ObjectId, prop: dict
    ) -> UserWatchlist | None:
        """
        Enrich a property with overview information.

        Args:
            prop_id (ObjectId): The property ID
            prop (dict): The base property information

        Returns:
            UserWatchlist | None: The enriched property information, or None if required data is missing
        """
        # Add property overview information
        prop_ov = await self._get_property_overview(prop_id)
        if not prop_ov:
            logger.warning(
                "Property overview not found for property %s, skipping",
                prop_id,
            )
            return None

        # Add common overview information
        common_ov = await self._get_common_overview(prop_id)
        if not common_ov:
            logger.warning(
                "Common overview not found for property %s, skipping",
                prop_id,
            )
            return None

        # Update with property overview data
        prop.update(
            {
                "is_active": True,
                "price": prop_ov["price"],
                "floor_plan": prop_ov["floor_plan"],
                "completion_time": prop_ov["completion_time"],
                "area": prop_ov["area"],
                "other_area": prop_ov["other_area"],
            }
        )

        # Update with common overview data
        prop.update(
            {
                "location": common_ov["location"],
                "transportation": common_ov["transportation"],
            }
        )

        # Only keep the first image URL if available
        if "image_urls" in prop and prop["image_urls"]:
            prop["image_urls"] = [prop["image_urls"][0]]

        try:
            return UserWatchlist(**prop)
        except Exception as e:
            logger.error(
                "Failed to create watchlist item for property %s: %s",
                prop_id,
                str(e),
            )
            return None

    async def _get_property_overview(
        self, prop_id: ObjectId
    ) -> PropertyOverview | None:
        """Get property overview information."""
        prop_ovs = await self.coll_prop_ovs.find({"property_id": prop_id}).to_list(
            length=1
        )
        return prop_ovs[0] if prop_ovs else None

    async def _get_common_overview(self, prop_id: ObjectId) -> CommonOverview | None:
        """Get common overview information."""
        common_ovs = await self.coll_common_ovs.find({"property_id": prop_id}).to_list(
            length=1
        )
        return common_ovs[0] if common_ovs else None
