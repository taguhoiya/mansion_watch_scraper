# """Tests for the watchlist_service module."""

# import os
# from unittest.mock import AsyncMock

# import pytest
# from bson import ObjectId
# from fastapi import HTTPException
# from pymongo.errors import (
#     ConnectionFailure,
#     OperationFailure,
#     ServerSelectionTimeoutError,
# )

# from app.services.watchlist_service import WatchlistService


# @pytest.fixture
# def mock_collections():
#     """Create mock collections for testing."""
#     mock_collections = {}
#     for coll_name in [
#         os.getenv("COLLECTION_USER_PROPERTIES"),
#         os.getenv("COLLECTION_PROPERTIES"),
#         os.getenv("COLLECTION_PROPERTY_OVERVIEWS"),
#         os.getenv("COLLECTION_COMMON_OVERVIEWS"),
#     ]:
#         mock_coll = AsyncMock()
#         mock_coll.find = AsyncMock()
#         mock_collections[coll_name] = mock_coll
#     return mock_collections


# @pytest.fixture
# def mock_db(mock_collections):
#     """Create a mock database for testing."""
#     db = AsyncMock()
#     db.__getitem__ = lambda self, key: mock_collections[key]
#     return db


# @pytest.fixture
# def service(mock_db):
#     """Create a WatchlistService instance for testing."""
#     return WatchlistService(mock_db)


# class TestWatchlistService:
#     """Test cases for WatchlistService."""

#     @pytest.mark.asyncio
#     async def test_get_user_watchlist_success(self, service):
#         """Test successful retrieval of user watchlist."""
#         # Set up mock returns
#         property_id = ObjectId("123456789012345678901234")

#         # Mock user properties collection
#         service.coll_user_props.find.return_value.to_list = AsyncMock(
#             return_value=[{"line_user_id": "test_user", "property_id": property_id}]
#         )

#         # Mock properties collection
#         service.coll_props.find.return_value.to_list = AsyncMock(
#             return_value=[
#                 {
#                     "_id": property_id,
#                     "name": "Test Property",
#                     "is_active": True,
#                     "image_urls": ["url1", "url2"],
#                 }
#             ]
#         )

#         # Mock property overviews collection
#         service.coll_prop_ovs.find.return_value.to_list = AsyncMock(
#             return_value=[
#                 {
#                     "property_id": property_id,
#                     "price": "1000万円",
#                     "floor_plan": "3LDK",
#                     "completion_time": "2020年",
#                     "area": "75.5m²",
#                     "other_area": "バルコニー10m²",
#                 }
#             ]
#         )

#         # Mock common overviews collection
#         service.coll_common_ovs.find.return_value.to_list = AsyncMock(
#             return_value=[
#                 {
#                     "property_id": property_id,
#                     "location": "Test Location",
#                     "transportation": ["渋谷駅徒歩10分"],
#                 }
#             ]
#         )

#         result = await service.get_user_watchlist("test_user")
#         assert len(result) == 1
#         assert result[0].property_id == str(property_id)
#         assert result[0].name == "Test Property"
#         assert result[0].is_active is True
#         assert result[0].image_urls == ["url1", "url2"]
#         assert result[0].price == "1000万円"
#         assert result[0].floor_plan == "3LDK"
#         assert result[0].completion_time == "2020年"
#         assert result[0].area == "75.5m²"
#         assert result[0].other_area == "バルコニー10m²"
#         assert result[0].location == "Test Location"
#         assert result[0].transportation == ["渋谷駅徒歩10分"]

#     @pytest.mark.asyncio
#     async def test_get_user_watchlist_no_properties(self, service):
#         """Test when user has no properties in watchlist."""
#         service.coll_user_props.find.return_value.to_list = AsyncMock(return_value=[])

#         with pytest.raises(HTTPException) as exc_info:
#             await service.get_user_watchlist("test_user")
#         assert exc_info.value.status_code == 404

#     @pytest.mark.asyncio
#     async def test_get_user_watchlist_connection_failure(self, service):
#         """Test handling of connection failure."""
#         service.coll_user_props.find.side_effect = ConnectionFailure()
#         with pytest.raises(HTTPException) as exc_info:
#             await service.get_user_watchlist("test_user")
#         assert exc_info.value.status_code == 503

#     @pytest.mark.asyncio
#     async def test_get_user_watchlist_operation_failure(self, service):
#         """Test handling of operation failure."""
#         service.coll_user_props.find.side_effect = OperationFailure("error")
#         with pytest.raises(HTTPException) as exc_info:
#             await service.get_user_watchlist("test_user")
#         assert exc_info.value.status_code == 503

#     @pytest.mark.asyncio
#     async def test_get_user_watchlist_server_selection_timeout(self, service):
#         """Test handling of server selection timeout."""
#         service.coll_user_props.find.side_effect = ServerSelectionTimeoutError()
#         with pytest.raises(HTTPException) as exc_info:
#             await service.get_user_watchlist("test_user")
#         assert exc_info.value.status_code == 503

#     @pytest.mark.asyncio
#     async def test_get_user_watchlist_missing_property_overview(self, service):
#         """Test handling of missing property overview."""
#         property_id = ObjectId("123456789012345678901234")

#         # Mock user properties collection
#         service.coll_user_props.find.return_value.to_list = AsyncMock(
#             return_value=[{"line_user_id": "test_user", "property_id": property_id}]
#         )

#         # Mock properties collection
#         service.coll_props.find.return_value.to_list = AsyncMock(
#             return_value=[
#                 {
#                     "_id": property_id,
#                     "name": "Test Property",
#                     "is_active": True,
#                     "image_urls": ["url1", "url2"],
#                 }
#             ]
#         )

#         # Mock empty property overviews collection
#         service.coll_prop_ovs.find.return_value.to_list = AsyncMock(return_value=[])

#         # Mock empty common overviews collection
#         service.coll_common_ovs.find.return_value.to_list = AsyncMock(return_value=[])

#         result = await service.get_user_watchlist("test_user")
#         assert len(result) == 1
#         assert result[0].property_id == str(property_id)
#         assert result[0].name == "Test Property"
#         assert result[0].is_active is True
#         assert result[0].image_urls == ["url1", "url2"]
#         assert result[0].price is None
#         assert result[0].floor_plan is None
#         assert result[0].completion_time is None
#         assert result[0].area is None
#         assert result[0].other_area is None
#         assert result[0].location is None
#         assert result[0].transportation == []

#     @pytest.mark.asyncio
#     async def test_get_user_watchlist_with_inactive_property(self, service):
#         """Test handling of inactive property."""
#         property_id = ObjectId("123456789012345678901234")

#         # Mock user properties collection
#         service.coll_user_props.find.return_value.to_list = AsyncMock(
#             return_value=[{"line_user_id": "test_user", "property_id": property_id}]
#         )

#         # Mock empty properties collection (property not found)
#         service.coll_props.find.return_value.to_list = AsyncMock(return_value=[])

#         with pytest.raises(HTTPException) as exc_info:
#             await service.get_user_watchlist("test_user")
#         assert exc_info.value.status_code == 404
