from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.apis.common_overviews import get_common_overview


@pytest.fixture
def sample_common_overview():
    return {
        "_id": ObjectId("67d50266b108f09557830e4f"),
        "property_id": ObjectId("67d50266b108f09557830e4e"),
        "location": "東京都新宿区",
        "交通": "JR山手線「新宿」駅 徒歩5分",
        "築年数": "2015年5月",
        "総戸数": "30戸",
        "created_at": "2023-01-01T00:00:00",
        "updated_at": "2023-01-01T00:00:00",
    }


class AsyncIterator:
    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index < len(self.items):
            item = self.items[self.index]
            self.index += 1
            return item
        raise StopAsyncIteration


@pytest.mark.asyncio
async def test_get_common_overview_invalid_id(monkeypatch):
    """Test get_common_overview with invalid property ID format."""
    with pytest.raises(HTTPException) as exc_info:
        await get_common_overview("invalid-id")

    assert exc_info.value.status_code == 400
    assert "Invalid property ID" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_common_overview_success(monkeypatch, sample_common_overview):
    """Test get_common_overview with valid property ID."""
    # Create mock collection with the find method returning sample data
    mock_coll = AsyncMock()
    mock_find = AsyncMock()

    mock_find.to_list = AsyncMock(return_value=[sample_common_overview])
    mock_coll.find = MagicMock(return_value=mock_find)

    # Create mock db with the collection method returning mock collection
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_coll

    # Mock get_db function to return mock db
    monkeypatch.setattr("app.apis.common_overviews.get_db", lambda: mock_db)

    # Mock to_json_serializable function
    def mock_to_json_serializable(obj):
        if isinstance(obj, dict):
            result = obj.copy()
            if "_id" in result:
                result["_id"] = str(result["_id"])
            if "property_id" in result:
                result["property_id"] = str(result["property_id"])
            return result
        return obj

    monkeypatch.setattr(
        "app.apis.common_overviews.to_json_serializable", mock_to_json_serializable
    )

    # Call the function with valid property ID
    result = await get_common_overview("67d50266b108f09557830e4e")

    # Assert that the find method was called with correct filter
    mock_coll.find.assert_called_once()
    call_args = mock_coll.find.call_args[0][0]
    assert "property_id" in call_args
    assert isinstance(call_args["property_id"], ObjectId)
    assert str(call_args["property_id"]) == "67d50266b108f09557830e4e"

    # Assert that the result matches expected data
    assert len(result) == 1
    assert result[0]["_id"] == str(sample_common_overview["_id"])
    assert result[0]["property_id"] == str(sample_common_overview["property_id"])
    assert result[0]["location"] == sample_common_overview["location"]
    assert result[0]["交通"] == sample_common_overview["交通"]


@pytest.mark.asyncio
async def test_get_common_overview_empty_result(monkeypatch):
    """Test get_common_overview with valid property ID but no data found."""
    # Create mock collection with the find method returning empty list
    mock_coll = AsyncMock()
    mock_find = AsyncMock()

    mock_find.to_list = AsyncMock(return_value=[])
    mock_coll.find = MagicMock(return_value=mock_find)

    # Create mock db with the collection method returning mock collection
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_coll

    # Mock get_db function to return mock db
    monkeypatch.setattr("app.apis.common_overviews.get_db", lambda: mock_db)

    # Call the function with valid property ID
    result = await get_common_overview("67d50266b108f09557830e4e")

    # Assert that the find method was called with correct filter
    mock_coll.find.assert_called_once()

    # Assert that the result is an empty list
    assert isinstance(result, list)
    assert len(result) == 0
