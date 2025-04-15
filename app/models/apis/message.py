"""API models for message endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.message import MessageStatus, MessageType


class MessageStatusResponse(BaseModel):
    """Response model for message status."""

    message_id: str = Field(..., description="Pub/Sub message ID")
    status: MessageStatus = Field(..., description="Current message status")
    message_type: MessageType = Field(..., description="Type of message")
    created_at: datetime = Field(..., description="Message creation time")
    updated_at: datetime = Field(..., description="Last message update time")
    result: Optional[Dict[str, Any]] = Field(
        None, description="Message result if completed"
    )
    error: Optional[str] = Field(None, description="Error message if failed")
    url: Optional[str] = Field(None, description="URL that was processed")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "message_id": "projects/my-project/topics/my-topic/messages/12345",
                "status": "failed",
                "message_type": "scrape",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z",
                "result": None,
                "error": "TimeoutError: Request timed out after 30 seconds",
                "url": "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/",
            }
        }


class MessageListResponse(BaseModel):
    """Response model for message list."""

    messages: List[MessageStatusResponse] = Field(..., description="List of messages")
    total: int = Field(..., description="Total number of messages matching the filter")
    limit: int = Field(..., description="Maximum number of messages returned")
    offset: int = Field(..., description="Offset used for pagination")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "messages": [
                    {
                        "message_id": "projects/my-project/topics/my-topic/messages/12345",
                        "status": "failed",
                        "message_type": "scrape",
                        "created_at": "2023-01-01T00:00:00Z",
                        "updated_at": "2023-01-01T00:01:00Z",
                        "result": None,
                        "error": "HttpError: Failed to fetch URL (404)",
                        "url": "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/",
                    }
                ],
                "total": 1,
                "limit": 10,
                "offset": 0,
            }
        }


class RetryMessageResponse(BaseModel):
    """Response model for retry message endpoint."""

    message: str = Field(..., description="Response message")
    original_message_id: str = Field(
        ..., description="ID of the original failed message"
    )
    new_message_id: str = Field(..., description="ID of the newly created message")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "message": "Retry initiated successfully",
                "original_message_id": "projects/my-project/topics/my-topic/messages/12345",
                "new_message_id": "projects/my-project/topics/my-topic/messages/67890",
            }
        }
