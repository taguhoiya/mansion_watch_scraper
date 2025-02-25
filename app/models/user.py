from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.id import PyObjectId


class User(BaseModel):
    id: Optional[PyObjectId] = Field(
        default=None,
        alias="_id",
        description="User ID",
    )
    line_user_id: str = Field(..., title="User ID from LINE")
    created_at: datetime = Field(..., title="the creation date of the user")
    updated_at: datetime = Field(..., title="the update date of the user")

    @field_validator("id")
    def validate_object_id(cls, v):
        return PyObjectId(v)

    @field_validator("line_user_id")
    def validate_user_id(cls, line_user_id: str) -> str:
        if not line_user_id.startswith("U"):
            raise ValueError("line_user_id must start with U")
        return line_user_id

    @model_validator(mode="after")
    def validate_timestamps(cls, model: "User") -> "User":
        if model.created_at and model.updated_at < model.created_at:
            raise ValueError("updated_at must be equal to or later than created_at")
        return model

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_schema_extra": {
            "example": {
                "id": "679f48bb824469aa5fc15392",
                "line_user_id": "U23b619197d01bab29b2c54955db6c2a1",
                "created_at": "2025-01-22T22:26:34.384Z",
                "updated_at": "2025-01-22T22:26:34.384Z",
            }
        },
    }
