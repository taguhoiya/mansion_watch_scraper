"""Message status model."""

import enum
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class MessageStatus(str, enum.Enum):
    """Message status enum."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MessageType(str, enum.Enum):
    """Message type enum."""

    SCRAPE = "scrape"


class Message(BaseModel):
    """Message model."""

    message_id: str = Field(..., description="Unique Pub/Sub message ID")
    message_type: MessageType = Field(..., description="Type of message")
    status: MessageStatus = Field(
        default=MessageStatus.PENDING, description="Current message status"
    )
    line_user_id: str = Field(
        ..., description="LINE user ID associated with the message"
    )
    url: Optional[str] = Field(None, description="URL to scrape (for scrape messages)")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Message creation time"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last message update time"
    )
    result: Optional[Dict[str, Any]] = Field(None, description="Message result data")
    error: Optional[str] = Field(None, description="Error message if message failed")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "message_id": "projects/my-project/topics/my-topic/messages/12345",
                "message_type": "scrape",
                "status": "failed",
                "line_user_id": "U1234567890abcdef",
                "url": "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z",
                "result": None,
                "error": "TimeoutError: Execution timed out after 300 seconds",
            }
        }
