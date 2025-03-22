"""MongoDB performance monitoring module."""

import logging
from functools import wraps
from time import perf_counter
from typing import Any, Callable, Dict

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.monitoring import CommandListener

logger = logging.getLogger(__name__)

# Define constants
SLOW_QUERY_THRESHOLD_MS = 100  # Threshold for slow query detection in milliseconds


class PerformanceCommandListener(CommandListener):
    """MongoDB command listener for performance monitoring."""

    def started(self, event):
        """Handle command started event."""
        logger.info(
            f"Command {event.command_name} started on database {event.database_name}"
        )

    def succeeded(self, event):
        """Handle command succeeded event."""
        duration_ms = event.duration_micros / 1000  # Convert to milliseconds
        if duration_ms > SLOW_QUERY_THRESHOLD_MS:
            logger.warning(
                f"Slow query detected: {event.command_name} took {duration_ms:.2f}ms"
            )
        else:
            logger.info(
                f"Command {event.command_name} completed in {duration_ms:.2f}ms"
            )

    def failed(self, event):
        """Handle command failed event."""
        logger.error(f"Command {event.command_name} failed with error: {event.failure}")


def monitor_performance(func: Callable) -> Callable:
    """Decorator to monitor function performance.

    Args:
        func: The function to monitor.

    Returns:
        The wrapped function.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = perf_counter()
        try:
            result = await func(*args, **kwargs)
            duration = (perf_counter() - start_time) * 1000
            logger.info(f"{func.__name__} completed in {duration:.2f}ms")
            return result
        except Exception as e:
            duration = (perf_counter() - start_time) * 1000
            logger.error(
                f"{func.__name__} failed after {duration:.2f}ms with error: {e}"
            )
            raise

    return wrapper


async def get_collection_stats(
    db: AsyncIOMotorDatabase, collection_name: str
) -> Dict[str, Any]:
    """Get statistics for a collection.

    Args:
        db: The database instance.
        collection_name: The name of the collection to get stats for.

    Returns:
        Collection statistics.
    """
    try:
        collection = db[collection_name]
        stats = await collection.stats()
        logger.info(f"Retrieved stats for collection {collection_name}")
        return stats
    except Exception as e:
        logger.error(f"Error getting collection stats: {e}")
        raise


async def analyze_query_performance(
    db: AsyncIOMotorDatabase, collection_name: str, query: dict
) -> Dict[str, Any]:
    """Analyze query performance using explain.

    Args:
        db: The database instance.
        collection_name: The name of the collection to analyze.
        query: The query to analyze.

    Returns:
        The query execution plan and statistics.
    """
    try:
        collection = db[collection_name]
        cursor = collection.find(query)
        explain_output = await cursor.explain("executionStats")
        logger.info(f"Analyzed query performance for {collection_name}")
        return explain_output
    except Exception as e:
        logger.error(f"Error analyzing query performance: {e}")
        raise
