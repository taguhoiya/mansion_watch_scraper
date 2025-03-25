import logging
import os
from concurrent import futures
from typing import Dict

from fastapi import APIRouter, HTTPException, status
from google.cloud import pubsub_v1
from pydantic import BaseModel, field_validator

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize Pub/Sub publisher client with batch settings
batch_settings = pubsub_v1.types.BatchSettings(
    max_bytes=1024 * 1024, max_latency=1, max_messages=100  # 1 MB  # 1 second
)
publisher = pubsub_v1.PublisherClient(batch_settings=batch_settings)

# Get project ID and topic name from environment variables
project_id = os.getenv("GCP_PROJECT_ID", "daring-night-451212-a8")
topic_name = os.getenv("PUBSUB_TOPIC", "mansion-watch-scraper-topic")
topic_path = publisher.topic_path(project_id, topic_name)


class ScrapeRequest(BaseModel):
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
            logger.warning(
                f"Published message {message_id} successfully"
            )  # Changed to warning
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

        # Publish message with callback
        future = publisher.publish(topic_path, data=message_data)
        logger.info(f"Published message {future} for URL: {request.url}")

        # Get message ID synchronously
        try:
            message_id = future.result(timeout=30)  # 30 seconds timeout
        except futures.TimeoutError:
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

    except Exception as e:
        logger.error(f"Error publishing message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error queuing scraping request: {str(e)}",
        )
