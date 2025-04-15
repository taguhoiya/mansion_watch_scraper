"""Failed message status API endpoints."""

import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.db.session import get_db
from app.models.apis.message import (
    MessageListResponse,
    MessageStatusResponse,
    RetryMessageResponse,
)
from app.models.message import MessageStatus, MessageType

router = APIRouter()
logger = logging.getLogger(__name__)


async def get_messages_collection() -> AsyncIOMotorCollection:
    """Get messages collection."""
    db: AsyncIOMotorDatabase = get_db()
    return db[os.getenv("COLLECTION_MESSAGES", "messages")]


@router.get(
    "/status/{message_id}",
    response_model=MessageStatusResponse,
    responses={
        status.HTTP_200_OK: {"description": "Failed message found"},
        status.HTTP_404_NOT_FOUND: {"description": "Failed message not found"},
    },
    summary="Get failed message status by message ID",
    description="Get the status of a failed message by its Pub/Sub message ID",
)
async def get_message_status(
    message_id: str = Path(..., description="Pub/Sub message ID of the failed message"),
    messages_collection: AsyncIOMotorCollection = Depends(get_messages_collection),
) -> MessageStatusResponse:
    """Get failed message status by message ID."""
    message = await messages_collection.find_one({"message_id": message_id})
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed message with message ID {message_id} not found",
        )

    # Convert MongoDB _id to string and format response
    message["_id"] = str(message["_id"])

    return MessageStatusResponse(
        message_id=message["message_id"],
        status=message["status"],
        message_type=message.get(
            "message_type", message.get("job_type")
        ),  # Support legacy job_type
        created_at=message["created_at"],
        updated_at=message["updated_at"],
        result=message.get("result"),
        error=message.get("error"),
        url=message.get("url"),
    )


@router.get(
    "/list",
    response_model=MessageListResponse,
    summary="List failed messages",
    description="List failed messages with optional filtering",
)
async def list_messages(
    limit: int = Query(
        10, description="Maximum number of messages to return", ge=1, le=100
    ),
    offset: int = Query(0, description="Offset for pagination", ge=0),
    line_user_id: Optional[str] = Query(None, description="Filter by LINE user ID"),
    start_date: Optional[str] = Query(
        None, description="Filter by start date (ISO format: YYYY-MM-DD)"
    ),
    end_date: Optional[str] = Query(
        None, description="Filter by end date (ISO format: YYYY-MM-DD)"
    ),
    messages_collection: AsyncIOMotorCollection = Depends(get_messages_collection),
) -> MessageListResponse:
    """List failed messages with optional filtering."""
    # Build filter dict - we only store failed messages
    filter_dict = {"status": MessageStatus.FAILED}
    if line_user_id:
        filter_dict["line_user_id"] = line_user_id

    # Add date range filters if provided
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter["$gte"] = f"{start_date}T00:00:00.000Z"
        if end_date:
            date_filter["$lte"] = f"{end_date}T23:59:59.999Z"
        if date_filter:
            filter_dict["created_at"] = date_filter

    # Get total count for the filter
    total = await messages_collection.count_documents(filter_dict)

    # Query messages
    cursor = (
        messages_collection.find(filter_dict)
        .sort("created_at", -1)  # Sort by creation time descending (newest first)
        .skip(offset)
        .limit(limit)
    )

    messages = []
    async for message in cursor:
        message["_id"] = str(message["_id"])
        messages.append(
            MessageStatusResponse(
                message_id=message["message_id"],
                status=message["status"],
                message_type=message.get(
                    "message_type", message.get("job_type")
                ),  # Support legacy job_type
                created_at=message["created_at"],
                updated_at=message["updated_at"],
                result=message.get("result"),
                error=message.get("error"),
                url=message.get("url"),
            )
        )

    return MessageListResponse(
        messages=messages,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/retry/{message_id}",
    response_model=RetryMessageResponse,
    responses={
        status.HTTP_200_OK: {"description": "Failed message retry initiated"},
        status.HTTP_404_NOT_FOUND: {"description": "Failed message not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Not a valid scrape message"},
    },
    summary="Retry a failed message",
    description="Retry a message that has previously failed by its Pub/Sub message ID",
)
async def retry_message(
    message_id: str = Path(..., description="Pub/Sub message ID of the failed message"),
    messages_collection: AsyncIOMotorCollection = Depends(get_messages_collection),
) -> RetryMessageResponse:
    """Retry a failed message."""
    # Find the original message
    message = await messages_collection.find_one({"message_id": message_id})
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed message with message ID {message_id} not found",
        )

    # Verify this is a failed message - with our new approach, all messages in the collection should be failed
    if message["status"] != MessageStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only failed messages can be retried. Current status: {message['status']}",
        )

    # Get the message_type (supporting legacy job_type field)
    message_type = message.get("message_type", message.get("job_type"))

    # Create a new scrape request
    if message_type != MessageType.SCRAPE or not message.get("url"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only scrape messages with a URL can be retried",
        )

    # Import here to avoid circular imports
    from app.apis.scrape import ScrapeRequest, queue_scraping

    # Create a scrape request object
    retry_request = ScrapeRequest(
        timestamp=datetime.utcnow(),
        url=message["url"],
        line_user_id=message["line_user_id"],
        check_only=False,  # Assume we want a full scrape on retry
    )

    # Queue a new scraping request
    response = await queue_scraping(retry_request, messages_collection)

    # Update the original message with retry info
    await messages_collection.update_one(
        {"message_id": message_id},
        {
            "$set": {
                "retried_at": datetime.utcnow(),
                "retry_message_id": response["message_id"],
            }
        },
    )

    return RetryMessageResponse(
        message="Retry initiated successfully",
        original_message_id=message_id,
        new_message_id=response["message_id"],
    )
