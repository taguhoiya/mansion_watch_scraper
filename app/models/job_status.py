from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.models.id import PyObjectId


class JobStatus(str, Enum):
    """Job processing status."""

    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    NOT_FOUND = "not_found"


class JobType(str, Enum):
    """Type of job being processed."""

    PROPERTY_SCRAPE = "property_scrape"
    BATCH_CHECK = "batch_check"


class JobTraceModel(BaseModel):
    """Model for tracking job/message processing status."""

    id: Optional[PyObjectId] = Field(
        default=None,
        alias="_id",
        description="Job trace ID",
    )
    message_id: str = Field(..., description="Pub/Sub message ID")
    job_type: JobType = Field(..., description="Type of job being processed")
    status: JobStatus = Field(
        default=JobStatus.QUEUED, description="Current status of the job"
    )
    url: Optional[str] = Field(
        default=None, description="URL being processed (for property scrapes)"
    )
    line_user_id: Optional[str] = Field(
        default=None, description="LINE user ID associated with the job"
    )
    check_only: bool = Field(
        default=False, description="Whether this is only a status check"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="When job was created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="When job status was last updated"
    )
    started_at: Optional[datetime] = Field(
        default=None, description="When processing started"
    )
    completed_at: Optional[datetime] = Field(
        default=None, description="When processing completed"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if job failed"
    )
    result: Optional[Dict[str, Any]] = Field(
        default=None, description="Result data if job succeeded"
    )

    class Config:
        """Pydantic model configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}
        populate_by_name = True
