"""MongoDB index management module.

Reference: https://www.mongodb.com/docs/manual/core/indexes-introduction/
"""

import logging
from typing import Any, Dict, List, Tuple

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel

logger = logging.getLogger(__name__)

# Define indexes for each collection
PROPERTY_INDEXES = [
    # Primary lookup index - must be unique
    IndexModel([("url", ASCENDING)], unique=True),
    # Compound index for status checks and sorting by update time
    # This can support: status queries, (status, updated_at) queries, and updated_at sorting
    IndexModel([("status", ASCENDING), ("updated_at", DESCENDING)]),
    # User property lookup index
    IndexModel([("line_user_id", ASCENDING)]),
    # Property search and filtering compound index
    # Supports queries that filter/sort by price, area and status
    IndexModel(
        [("price", ASCENDING), ("area", ASCENDING), ("status", ASCENDING)],
    ),
]

USER_PROPERTY_INDEXES = [
    # Primary compound index for user-property relationship
    IndexModel(
        [("line_user_id", ASCENDING), ("property_id", ASCENDING)],
        unique=True,
    ),
    # Support for chronological listing of user properties
    IndexModel([("created_at", DESCENDING)]),
]

COLLECTION_INDEXES = {
    "properties": PROPERTY_INDEXES,
    "user_properties": USER_PROPERTY_INDEXES,
}


def get_index_key_tuple(index: Dict[str, Any]) -> Tuple[Tuple[str, int], ...]:
    """Convert index key to a tuple for comparison.

    Args:
        index: The index document.

    Returns:
        A tuple of (field_name, direction) tuples.
    """
    # Handle the case where key is a list of tuples
    if isinstance(index["key"], list):
        return tuple(tuple(item) for item in index["key"])
    # Handle the case where key is a dict
    return tuple(tuple(item) for item in index["key"].items())


async def get_existing_indexes(
    collection: AsyncIOMotorCollection,
) -> List[Dict[str, Any]]:
    """Get existing indexes from a collection.

    Args:
        collection: The collection to get indexes from.

    Returns:
        A list of existing index documents.

    Raises:
        Exception: If there is an error listing indexes.
    """
    try:
        existing_indexes = []
        cursor = collection.list_indexes()
        async for index in cursor:
            existing_indexes.append(index)
        return existing_indexes
    except Exception as e:
        logger.error(f"Error listing indexes: {e}")
        raise


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Ensure all required indexes exist in the database.

    Args:
        db: The database instance to create indexes on.

    Raises:
        Exception: If there is an error listing or creating indexes.
    """
    for collection_name, indexes in COLLECTION_INDEXES.items():
        collection = db[collection_name]
        existing_indexes = await get_existing_indexes(collection)

        # Create missing indexes
        try:
            for index in indexes:
                if not any(
                    get_index_key_tuple(existing) == get_index_key_tuple(index.document)
                    for existing in existing_indexes
                ):
                    await collection.create_indexes([index])
                    logger.info(
                        f"Created index {index.document['key']} on collection {collection_name}"
                    )
        except Exception as e:
            logger.error(
                f"Error creating indexes for collection {collection_name}: {e}"
            )
            raise
