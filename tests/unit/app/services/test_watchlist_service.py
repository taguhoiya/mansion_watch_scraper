import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.watchlist_service import WatchlistService


@pytest.mark.watchlist
class TestWatchlistService:
    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create a mock database."""
        db = AsyncMock(spec=AsyncIOMotorDatabase)
        collections = {}
        for coll_name in [
            "properties",
            "user_properties",
            "property_overviews",
            "common_overviews",
        ]:
            mock_collection = AsyncMock()
            # Create a mock cursor that properly handles to_list
            mock_cursor = AsyncMock()
            mock_cursor.to_list = AsyncMock()
            # Make find() return the cursor
            mock_collection.find = MagicMock(return_value=mock_cursor)
            collections[coll_name] = mock_collection

        # Use __getitem__ to handle dictionary-style access
        db.__getitem__ = MagicMock(side_effect=lambda x: collections[x])
        return db

    @pytest.fixture
    def service(self, mock_db) -> WatchlistService:
        """Create a WatchlistService instance with mock database."""
        with patch.dict(
            os.environ,
            {
                "COLLECTION_PROPERTIES": "properties",
                "COLLECTION_USER_PROPERTIES": "user_properties",
                "COLLECTION_PROPERTY_OVERVIEWS": "property_overviews",
                "COLLECTION_COMMON_OVERVIEWS": "common_overviews",
            },
        ):
            return WatchlistService(mock_db)

    @pytest.mark.asyncio
    async def test_get_user_watchlist_empty(self, service: WatchlistService):
        """Test getting an empty watchlist."""
        # Setup
        service.coll_user_props.find.return_value.to_list.return_value = []

        # Test
        with pytest.raises(HTTPException) as exc_info:
            await service.get_user_watchlist("test_user")

        # Verify
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "User properties not found"

    @pytest.mark.asyncio
    async def test_get_user_watchlist_success(self, service: WatchlistService):
        """Test getting a watchlist with properties."""
        # Setup mock data
        property_id = ObjectId()
        user_props = [{"property_id": property_id, "line_user_id": "test_user"}]
        property_data = {
            "_id": property_id,
            "name": "Test Property",
            "url": "https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/",
            "image_urls": [
                "https://example.com/image1.jpg",
                "https://example.com/image2.jpg",
            ],
            "is_active": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        property_overview = {
            "property_id": property_id,
            "price": "5000万円",
            "floor_plan": "3LDK",
            "completion_time": "2020年",
            "area": "75.5m²",
            "other_area": "バルコニー10m²",
        }
        common_overview = {
            "property_id": property_id,
            "location": "東京都渋谷区",
            "transportation": ["渋谷駅徒歩5分", "表参道駅徒歩8分"],
        }

        # Setup mock returns
        service.coll_user_props.find.return_value.to_list.return_value = user_props
        service.coll_props.find.return_value.to_list.return_value = [property_data]
        service.coll_prop_ovs.find.return_value.to_list.return_value = [
            property_overview
        ]
        service.coll_common_ovs.find.return_value.to_list.return_value = [
            common_overview
        ]

        # Test
        result = await service.get_user_watchlist("test_user")

        # Assert
        assert len(result) == 1
        assert result[0].id == str(property_id)
        assert result[0].name == "Test Property"
        assert result[0].url == "https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/"
        assert result[0].is_active is True
        assert result[0].price == "5000万円"
        assert result[0].floor_plan == "3LDK"
        assert result[0].completion_time == "2020年"
        assert result[0].area == "75.5m²"
        assert result[0].other_area == "バルコニー10m²"
        assert result[0].location == "東京都渋谷区"
        assert result[0].transportation == ["渋谷駅徒歩5分", "表参道駅徒歩8分"]
        assert len(result[0].image_urls) == 1

    @pytest.mark.asyncio
    async def test_get_user_watchlist_missing_overviews(
        self, service: WatchlistService
    ):
        """Test getting a watchlist when some overviews are missing."""
        # Setup mock data
        property_id = ObjectId()
        user_props = [{"property_id": property_id, "line_user_id": "test_user"}]
        property_data = {
            "_id": property_id,
            "name": "Test Property",
            "url": "https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/",
            "image_urls": ["https://example.com/image1.jpg"],
            "is_active": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "price": "5000万円",
            "floor_plan": "3LDK",
            "completion_time": "2020年",
            "area": "75.5m²",
            "other_area": "バルコニー10m²",
            "location": "東京都渋谷区",
            "transportation": ["渋谷駅徒歩5分"],
        }

        # Setup mock returns - no overviews found
        service.coll_user_props.find.return_value.to_list.return_value = user_props
        service.coll_props.find.return_value.to_list.return_value = [property_data]
        service.coll_prop_ovs.find.return_value.to_list.return_value = []
        service.coll_common_ovs.find.return_value.to_list.return_value = []

        # Test
        result = await service.get_user_watchlist("test_user")

        # Assert
        assert len(result) == 1
        assert result[0].id == str(property_id)
        assert result[0].name == "Test Property"
        assert result[0].url == "https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/"
        assert result[0].is_active is True
        assert result[0].price == "5000万円"
        assert result[0].floor_plan == "3LDK"
        assert result[0].completion_time == "2020年"
        assert result[0].area == "75.5m²"
        assert result[0].other_area == "バルコニー10m²"
        assert result[0].location == "東京都渋谷区"
        assert result[0].transportation == ["渋谷駅徒歩5分"]
        assert len(result[0].image_urls) == 1

    @pytest.mark.asyncio
    async def test_get_user_watchlist_no_images(self, service: WatchlistService):
        """Test getting a watchlist for a property without images."""
        # Setup mock data
        property_id = ObjectId()
        user_props = [{"property_id": property_id, "line_user_id": "test_user"}]
        property_data = {
            "_id": property_id,
            "name": "Test Property",
            "url": "https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/",
            "is_active": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "price": "5000万円",
            "floor_plan": "3LDK",
            "completion_time": "2020年",
            "area": "75.5m²",
            "other_area": "バルコニー10m²",
            "location": "東京都渋谷区",
            "transportation": ["渋谷駅徒歩5分"],
        }

        # Setup mock returns
        service.coll_user_props.find.return_value.to_list.return_value = user_props
        service.coll_props.find.return_value.to_list.return_value = [property_data]
        service.coll_prop_ovs.find.return_value.to_list.return_value = []
        service.coll_common_ovs.find.return_value.to_list.return_value = []

        # Test
        result = await service.get_user_watchlist("test_user")

        # Assert
        assert len(result) == 1
        assert result[0].id == str(property_id)
        assert result[0].name == "Test Property"
        assert result[0].url == "https://suumo.jp/ms/mansion/tokyo/sc_shinjuku/"
        assert result[0].is_active is True
        assert result[0].price == "5000万円"
        assert result[0].floor_plan == "3LDK"
        assert result[0].completion_time == "2020年"
        assert result[0].area == "75.5m²"
        assert result[0].other_area == "バルコニー10m²"
        assert result[0].location == "東京都渋谷区"
        assert result[0].transportation == ["渋谷駅徒歩5分"]
        assert len(result[0].image_urls) == 0
