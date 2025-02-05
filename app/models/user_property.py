from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.id import PyObjectId


class UserProperty(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    line_user_id: str = Field(..., title="the user id from LINE")
    property_id: PyObjectId = Field(..., title="the id of the property")
    last_aggregated_at: datetime = Field(
        ..., title="the last aggregated time, which is the start of aggregated time"
    )
    next_aggregated_at: datetime = Field(
        ...,
        title="the next aggregated time, which is 3 days later from the last aggregated time",
    )
    first_succeeded_at: datetime = Field(
        ..., title="the first succeeded time of aggregation, which is the created time"
    )
    last_succeeded_at: datetime = Field(
        ...,
        title="the last succeeded time of aggregation, which is the end of aggregated time",
    )

    @field_validator("id", "property_id")
    def validate_object_id(cls, v):
        return PyObjectId(v)

    @field_validator("line_user_id")
    def validate_line_user_id(cls, line_user_id):
        if not line_user_id.startswith("U"):
            raise ValueError("line_user_id must start with U")

    @field_validator("last_succeeded_at")
    def validate_succeeded_timestamps(cls, last_succeeded_at, values):
        first_succeeded_at = values.get("first_succeeded_at")
        last_aggregated_at = values.get("last_aggregated_at")
        if first_succeeded_at and last_succeeded_at < first_succeeded_at:
            raise ValueError(
                "last_succeeded_at must be equal to or later than first_succeeded_at"
            )
        elif last_aggregated_at and last_aggregated_at <= last_succeeded_at:
            raise ValueError(
                "last_succeeded_at must be equal to or earlier than last_aggregated_at"
            )
        return last_succeeded_at

    @field_validator("next_aggregated_at")
    def validate_aggregated_times(cls, next_aggregated_at, values):
        last_aggregated_at = values.get("last_aggregated_at")
        if last_aggregated_at and next_aggregated_at < last_aggregated_at:
            raise ValueError("next_aggregated_at must be later than last_aggregated_at")
        return next_aggregated_at

    class Config:
        json_schema_extra = {
            "example": {
                "line_user_id": "U23b619197d01bab29b2c54955db6c2a1",
                "property_id": "679f48bb824469aa5fc15392",
                "last_aggregated_at": "2021-01-01T01:00:00",
                "next_aggregated_at": "2021-01-04T00:00:00",
                "first_succeeded_at": "2021-01-01T00:00:00",
                "last_succeeded_at": "2021-01-01T02:00:00",
            }
        }
