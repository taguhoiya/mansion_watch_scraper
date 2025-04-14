import logging
import os
from concurrent import futures
from datetime import datetime
from typing import Dict

from fastapi import APIRouter, HTTPException, status
from google.cloud import pubsub_v1
from pydantic import BaseModel, field_validator

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize Pub/Sub settings
batch_settings = pubsub_v1.types.BatchSettings(
    max_bytes=1024 * 1024, max_latency=1, max_messages=100  # 1 MB  # 1 second
)

_publisher = None
_publisher_options = None


def get_publisher(line_user_id: str = None):
    """Get or create Pub/Sub publisher client with batch settings.

    Args:
        line_user_id: Optional LINE user ID (stored but not used for ordering)

    Returns:
        PublisherClient: The Pub/Sub publisher client
    """
    global _publisher, _publisher_options

    # Store the line_user_id for logging purposes
    if line_user_id and _publisher_options != line_user_id:
        _publisher_options = line_user_id

    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient(batch_settings=batch_settings)

    return _publisher


def get_topic_path():
    """Get the full topic path for Pub/Sub."""
    # Get project ID and topic name from environment variables
    project_id = os.getenv("GCP_PROJECT_ID", "daring-night-451212-a8")
    topic_name = os.getenv("PUBSUB_TOPIC", "mansion-watch-scraper-topic")
    # Call get_publisher with no parameters since we don't need ordering for this call
    return get_publisher().topic_path(project_id, topic_name)


class ScrapeRequest(BaseModel):
    timestamp: datetime
    url: str
    line_user_id: str
    check_only: bool = False  # If True, only check if property exists

    @field_validator("line_user_id")
    def validate_line_user_id(cls, v):
        """Validate that line_user_id starts with 'U'."""
        if not v.startswith("U"):
            raise ValueError("line_user_id must start with U")
        return v

    @field_validator("url")
    def validate_url(cls, v):
        """Validate that url is a valid URL."""
        if not v.startswith("https://suumo.jp/ms"):
            raise ValueError("url must start with https://suumo.jp/ms")
        return v


def get_callback(future: futures.Future, message_id: str) -> None:
    """Get callback function for the published message."""

    def callback(future: futures.Future) -> None:
        try:
            future.result()
        except Exception as e:
            logger.error(f"Publishing message {message_id} failed: {e}")

    return callback


@router.post(
    "/scrape",
    summary="Queue a scraping request",
    response_description="Scraping request status",
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_scraping(request: ScrapeRequest) -> Dict[str, str]:
    """
    Queue a scraping request via Pub/Sub.

    Args:
        request: The scraping request containing URL and user ID

    Returns:
        Dictionary containing the status of the request
    """
    try:
        # Prepare message data
        logger.info(f"Publishing message for URL: {request.url}")
        message_data = request.model_dump_json().encode("utf-8")

        # Get publisher and topic path
        publisher = get_publisher(request.line_user_id)
        topic_path = get_topic_path()

        # Publish message with callback
        future = publisher.publish(topic_path, data=message_data)

        # Get message ID synchronously
        try:
            message_id = future.result(timeout=30)  # 30 seconds timeout
        except futures.TimeoutError:
            logger.error("Timeout while publishing message")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Timeout while publishing message",
            )

        # Add callback for async handling
        future.add_done_callback(get_callback(future, message_id))

        logger.info(f"Published message {message_id} for URL: {request.url}")
        return {
            "status": "queued",
            "message": "Scraping request has been queued",
            "message_id": message_id,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error publishing message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error queuing scraping request: {str(e)}",
        )
