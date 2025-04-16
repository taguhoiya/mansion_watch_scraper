from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.apis.users import get_property_watchlist
from app.models.apis.watchlist import UserWatchlist
from app.services.watchlist_service import WatchlistService


@pytest.fixture
def sample_user_property():
    return {
        "_id": ObjectId("67d50266b108f09557830e51"),
        "line_user_id": "user123",
        "property_id": ObjectId("67d50266b108f09557830e4e"),
        "created_at": "2023-01-01T00:00:00",
        "updated_at": "2023-01-01T00:00:00",
    }


@pytest.fixture
def sample_property():
    return {
        "_id": ObjectId("67d50266b108f09557830e4e"),
        "name": "テスト物件",
        "url": "https://suumo.jp/ms/chuko/tokyo/sc_minato/nc_75709932/",
        "price": "6,780万円",
        "created_at": "2023-01-01T00:00:00",
        "updated_at": "2023-01-01T00:00:00",
        "is_active": True,
        "floor_plan": "3LDK",
        "completion_time": "2015年5月",
        "area": "65.75m²",
        "other_area": "バルコニー 10.8m²",
        "location": "東京都新宿区",
        "transportation": ["JR山手線「新宿」駅 徒歩5分"],
        "image_urls": [
            "https://example.com/image1.jpg",
            "https://example.com/image2.jpg",
        ],
    }


@pytest.fixture
def sample_watchlist_item():
    return UserWatchlist(
        _id="67d50266b108f09557830e4e",
        name="テスト物件",
        url="https://suumo.jp/ms/chuko/tokyo/sc_minato/nc_75709932/",
        price="6,780万円",
        created_at="2023-01-01T00:00:00",
        updated_at="2023-01-01T00:00:00",
        is_active=True,
        floor_plan="3LDK",
        completion_time="2015年5月",
        area="65.75m²",
        other_area="バルコニー 10.8m²",
        location="東京都新宿区",
        transportation=["JR山手線「新宿」駅 徒歩5分"],
        image_urls=["https://example.com/image1.jpg"],
    )


@pytest.mark.asyncio
async def test_get_property_watchlist_success(sample_watchlist_item):
    """Test successful retrieval of user's watchlist."""
    # Create mock watchlist service
    mock_service = MagicMock(spec=WatchlistService)
    mock_service.get_user_watchlist = AsyncMock(return_value=[sample_watchlist_item])

    # Call the API function
    result = await get_property_watchlist("user123", None, mock_service)

    # Verify the service was called with correct arguments
    mock_service.get_user_watchlist.assert_called_once_with("user123")

    # Verify the result matches expected output
    assert len(result) == 1
    assert result[0].model_dump() == sample_watchlist_item.model_dump()


@pytest.mark.asyncio
async def test_get_property_watchlist_not_found():
    """Test watchlist retrieval when user properties are not found."""
    # Create mock watchlist service that raises HTTPException
    mock_service = MagicMock(spec=WatchlistService)
    mock_service.get_user_watchlist = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="User properties not found")
    )

    # Call the API function and expect an exception
    with pytest.raises(HTTPException) as exc_info:
        await get_property_watchlist("nonexistent_user", None, mock_service)

    # Verify the exception details
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "User properties not found"


@pytest.mark.asyncio
async def test_get_property_watchlist_service_error():
    """Test handling of service errors."""
    # Create mock watchlist service that raises a generic exception
    error_message = "Database connection error"
    mock_service = MagicMock(spec=WatchlistService)
    mock_service.get_user_watchlist = AsyncMock(side_effect=Exception(error_message))

    # Call the API function and expect an HTTPException to be raised
    with pytest.raises(HTTPException) as exc_info:
        await get_property_watchlist("user123", None, mock_service)

    # Verify the exception details - the error detail should be the string representation of the original exception
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == error_message


@pytest.mark.asyncio
async def test_get_property_watchlist_empty():
    """Test case when user has no properties in watchlist."""
    # Create mock watchlist service returning empty list
    mock_service = MagicMock(spec=WatchlistService)
    mock_service.get_user_watchlist = AsyncMock(return_value=[])

    # Call the API function
    result = await get_property_watchlist("user123", None, mock_service)

    # Verify the result is an empty list
    assert isinstance(result, list)
    assert len(result) == 0
