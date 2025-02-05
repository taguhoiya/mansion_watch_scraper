from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.id import PyObjectId


class User(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    line_user_id: str = Field(..., title="the user id from LINE")
    creted_at: str = Field(..., title="the creation date of the user")
    updated_at: str = Field(..., title="the update date of the user")

    @field_validator("id")
    def validate_object_id(cls, v):
        return PyObjectId(v)

    @field_validator("line_user_id")
    def validate_user_id(cls, line_user_id):
        if not line_user_id.startswith("U"):
            raise ValueError("line_user_id must start with U")

    @field_validator("created_at", "updated_at")
    def validate_timestamps(cls, created_at, updated_at):
        if created_at and updated_at < created_at:
            raise ValueError("updated_at must be equal to or later than created_at")
        return updated_at

    class Config:
        json_schema_extra = {
            "example": {
                "line_user_id": "U23b619197d01bab29b2c54955db6c2a1",
                "created_at": "2025-01-22T22:26:34.384Z",
                "updated_at": "2025-01-22T22:26:34.384Z",
            }
        }
