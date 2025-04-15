"""MongoDB index management module.

Reference: https://www.mongodb.com/docs/manual/core/indexes-introduction/
"""

import logging
from typing import Any, Dict, List, Tuple, Union

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

MESSAGE_INDEXES = [
    # Primary lookup index - must be unique
    IndexModel([("message_id", ASCENDING)], unique=True),
    # Index for finding messages by LINE user ID and status
    IndexModel([("line_user_id", ASCENDING), ("status", ASCENDING)]),
    # Index for sorting by creation and update times
    IndexModel([("created_at", DESCENDING)]),
    IndexModel([("updated_at", DESCENDING)]),
]

COLLECTION_INDEXES = {
    "properties": PROPERTY_INDEXES,
    "user_properties": USER_PROPERTY_INDEXES,
    "messages": MESSAGE_INDEXES,
}


def get_index_key_tuple(
    index_key: Union[Dict[str, Any], List[Tuple[str, Any]], IndexModel],
) -> Tuple[Tuple[str, Any], ...]:
    """Convert an index key to a tuple for comparison.

    Args:
        index_key: The index key to convert. Can be a dictionary, list of tuples, or IndexModel.

    Returns:
        A tuple of (field, direction) pairs.
    """
    if isinstance(index_key, IndexModel):
        return tuple((str(k), v) for k, v in index_key.document["key"].items())
    if isinstance(index_key, list):
        return tuple((str(k), v) for k, v in index_key)
    return tuple(sorted((str(k), v) for k, v in index_key.items()))


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
        cursor = collection.list_indexes()
        existing_indexes = []

        # Handle both cursor and coroutine returns
        if hasattr(cursor, "__aiter__"):
            async for index in cursor:
                existing_indexes.append(index)
        else:
            # If it's a coroutine, await it to get the cursor
            cursor = await cursor

            async for index in cursor:
                existing_indexes.append(index)

        return existing_indexes
    except Exception as e:
        logger.error(f"Error listing indexes: {str(e)}")
        raise


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Ensure all required indexes exist.

    Args:
        db: The database instance.

    Raises:
        Exception: If there is an error creating indexes.
    """
    for collection_name, indexes in COLLECTION_INDEXES.items():
        collection = db[collection_name]
        try:
            logger.info("Checking indexes for collection: %s", collection_name)
            existing_indexes = await get_existing_indexes(collection)
            existing_index_keys = {
                get_index_key_tuple(index.get("key", {})) for index in existing_indexes
            }

            indexes_to_create = []
            for index in indexes:
                index_key_tuple = get_index_key_tuple(index)
                if index_key_tuple in existing_index_keys:
                    logger.info(
                        "Index already exists: %s on %s",
                        index.document["key"],
                        collection_name,
                    )
                else:
                    logger.info(
                        "Index needs to be created: %s on %s",
                        index.document["key"],
                        collection_name,
                    )
                    indexes_to_create.append(index)

            if indexes_to_create:
                logger.info(
                    "Creating %d indexes on collection %s",
                    len(indexes_to_create),
                    collection_name,
                )
                await collection.create_indexes(indexes_to_create)
                logger.info(
                    "Successfully created indexes on collection %s",
                    collection_name,
                )
            else:
                logger.info(
                    "All required indexes already exist on collection %s",
                    collection_name,
                )

        except Exception as e:
            logger.error(
                "Error ensuring indexes on collection %s: %s",
                collection_name,
                str(e),
            )
            raise
