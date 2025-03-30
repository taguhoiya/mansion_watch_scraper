from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.id import PyObjectId


class UserProperty(BaseModel):
    """Model representing a user's property subscription for aggregation."""

    id: Optional[PyObjectId] = Field(
        default=None,
        alias="_id",
        description="User property ID",
    )
    line_user_id: Optional[str] = Field(
        default=None, description="User ID from LINE platform"
    )
    property_id: Optional[PyObjectId] = Field(
        default=None, description="ID of the property being tracked"
    )
    last_aggregated_at: Optional[datetime] = Field(
        default=None, description="Start time of the last aggregation period"
    )
    next_aggregated_at: Optional[datetime] = Field(
        default=None,
        description="Scheduled time for the next aggregation (typically 3 days after last_aggregated_at)",
    )
    first_succeeded_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of first successful aggregation (creation time)",
    )
    last_succeeded_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of most recent successful aggregation",
    )

    @field_validator("property_id")
    @classmethod
    def validate_object_id(cls, v) -> PyObjectId:
        """Convert and validate property ID as ObjectId."""
        return PyObjectId(v)

    @field_validator("line_user_id")
    def validate_line_user_id(cls, line_user_id: str) -> str:
        """Ensure LINE user ID follows the expected format."""
        if not line_user_id.startswith("U"):
            raise ValueError("LINE user ID must start with 'U'")
        return line_user_id

    @field_validator("next_aggregated_at")
    def validate_next_aggregation_time(
        cls, next_time: datetime, values: dict
    ) -> datetime:
        """Ensure next_aggregated_at is after last_aggregated_at."""
        last_time = values.data.get("last_aggregated_at")
        if last_time and next_time <= last_time:
            raise ValueError(
                "Next aggregation time must be later than last aggregation time"
            )
        return next_time

    @field_validator("last_succeeded_at")
    def validate_success_timestamps(
        cls, last_success: Optional[datetime], values: dict
    ) -> Optional[datetime]:
        """Validate timestamp relationships for successful aggregations."""
        if last_success is None:
            return None

        first_success = values.data.get("first_succeeded_at")
        last_aggregated = values.data.get("last_aggregated_at")

        # Validate against first_succeeded_at
        if first_success and last_success < first_success:
            raise ValueError(
                "Last success time cannot be earlier than first success time"
            )

        # Validate against last_aggregated_at
        if last_aggregated and last_success > last_aggregated:
            raise ValueError(
                "Last success time cannot be later than last aggregation time"
            )

        return last_success

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_schema_extra": {
            "example": {
                "_id": "679f48bb824469aa5fc15392",
                "line_user_id": "U23b619197d01bab29b2c54955db6c2a1",
                "property_id": "679f48bb824469aa5fc15392",
                "last_aggregated_at": "2021-01-01T01:00:00",
                "next_aggregated_at": "2021-01-04T00:00:00",
                "first_succeeded_at": "2021-01-01T00:00:00",
                "last_succeeded_at": "2021-01-01T02:00:00",
            }
        },
    }
