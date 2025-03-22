"""Test MongoDB index management module."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from app.db.indexes import COLLECTION_INDEXES, ensure_indexes, get_index_key_tuple


@pytest.fixture
def mock_db():
    """Create a mock database for testing."""
    db = MagicMock(spec=AsyncIOMotorDatabase)
    mock_collection = AsyncMock()
    db.__getitem__.return_value = mock_collection
    return db


@pytest.mark.asyncio
async def test_ensure_indexes_handles_errors(mock_db: AsyncIOMotorDatabase):
    """Test that ensure_indexes handles errors gracefully."""
    # Make the collection.create_indexes method raise an exception
    mock_db["properties"].create_indexes.side_effect = Exception("Test error")

    with pytest.raises(Exception, match="Test error"):
        await ensure_indexes(mock_db)


@pytest.mark.asyncio
async def test_index_definitions():
    """Test that index definitions are correct."""
    property_indexes = COLLECTION_INDEXES["properties"]
    user_property_indexes = COLLECTION_INDEXES["user_properties"]

    # Print index keys for debugging
    for idx in property_indexes:
        print(f"Index key: {get_index_key_tuple(idx.document)}")

    # Check URL index
    url_index = next(
        (
            idx
            for idx in property_indexes
            if get_index_key_tuple(idx.document) == (("url", ASCENDING),)
        ),
        None,
    )
    assert url_index is not None
    assert url_index.document.get("unique") is True

    # Check status and updated_at compound index
    status_updated_index = next(
        (
            idx
            for idx in property_indexes
            if get_index_key_tuple(idx.document)
            == (("status", ASCENDING), ("updated_at", DESCENDING))
        ),
        None,
    )
    assert status_updated_index is not None

    # Check line_user_id index
    line_user_id_index = next(
        (
            idx
            for idx in property_indexes
            if get_index_key_tuple(idx.document) == (("line_user_id", ASCENDING),)
        ),
        None,
    )
    assert line_user_id_index is not None

    # Check property search compound index
    search_index = next(
        (
            idx
            for idx in property_indexes
            if get_index_key_tuple(idx.document)
            == (
                ("price", ASCENDING),
                ("area", ASCENDING),
                ("status", ASCENDING),
            )
        ),
        None,
    )
    assert search_index is not None

    # Check user property indexes
    user_property_primary = next(
        (
            idx
            for idx in user_property_indexes
            if get_index_key_tuple(idx.document)
            == (("line_user_id", ASCENDING), ("property_id", ASCENDING))
        ),
        None,
    )
    assert user_property_primary is not None
    assert user_property_primary.document.get("unique") is True

    created_at_index = next(
        (
            idx
            for idx in user_property_indexes
            if get_index_key_tuple(idx.document) == (("created_at", DESCENDING),)
        ),
        None,
    )
    assert created_at_index is not None
