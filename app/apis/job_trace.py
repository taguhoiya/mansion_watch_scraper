import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from mansion_watch_scraper.pubsub.job_trace import get_job_status, get_jobs_for_user

router = APIRouter()
logger = logging.getLogger(__name__)


class JobStatusResponse(BaseModel):
    """Response model for job status endpoint."""

    id: str = Field(..., description="Job trace ID")
    message_id: str = Field(..., description="Pub/Sub message ID")
    status: str = Field(..., description="Current job status")
    url: Optional[str] = Field(None, description="URL being processed")
    line_user_id: Optional[str] = Field(None, description="LINE user ID")
    check_only: bool = Field(
        False, description="Whether this is a check-only operation"
    )
    created_at: str = Field(..., description="When job was created")
    updated_at: str = Field(..., description="When job was last updated")
    started_at: Optional[str] = Field(None, description="When processing started")
    completed_at: Optional[str] = Field(None, description="When processing completed")
    error: Optional[str] = Field(None, description="Error message if job failed")
    result: Optional[Dict[str, Any]] = Field(
        None, description="Result data if job succeeded"
    )


class UserJobsResponse(BaseModel):
    """Response model for user jobs endpoint."""

    jobs: List[JobStatusResponse] = Field(..., description="List of job traces")
    total_count: int = Field(..., description="Total number of jobs for user")
    limit: int = Field(..., description="Maximum number of jobs returned")
    skip: int = Field(..., description="Number of jobs skipped")


@router.get(
    "/status/{message_id}",
    response_model=JobStatusResponse,
    summary="Get job status by message ID",
    status_code=status.HTTP_200_OK,
)
async def get_job_trace_status(message_id: str) -> Dict[str, Any]:
    """
    Get the status of a job by its message ID.

    Args:
        message_id: The Pub/Sub message ID

    Returns:
        Job trace information
    """
    job_trace = get_job_status(message_id)
    if not job_trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job trace not found for message ID: {message_id}",
        )

    # MongoDB's _id is returned as string already by get_job_status
    job_trace["id"] = job_trace.pop("_id")

    return job_trace


@router.get(
    "/user/{line_user_id}",
    response_model=UserJobsResponse,
    summary="Get jobs for a specific user",
    status_code=status.HTTP_200_OK,
)
async def get_user_jobs(
    line_user_id: str,
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """
    Get all job traces for a specific user.

    Args:
        line_user_id: The LINE user ID
        limit: Maximum number of jobs to return (1-100)
        skip: Number of jobs to skip for pagination

    Returns:
        Dict containing jobs and pagination info
    """
    jobs, total_count = get_jobs_for_user(line_user_id, limit, skip)

    # Change _id to id for all jobs
    for job in jobs:
        job["id"] = job.pop("_id")

    return {
        "jobs": jobs,
        "total_count": total_count,
        "limit": limit,
        "skip": skip,
    }
