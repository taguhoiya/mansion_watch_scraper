from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# {
#     "_id": {"$oid": "6790f20a4dffe24d21125ae6"},
#     "property_name": "クレヴィア渋谷富ヶ谷",
#     "url": "https://suumo.jp/ms/chuko/tokyo/sc_shibuya/nc_76483805/",
#     "created_at": {"$date": "2025-01-22T22:26:34.384Z"},
#     "updated_at": {"$date": "2025-01-22T22:26:34.384Z"},
# }


class Property(BaseModel):
    name: str = Field(..., title="the name of the property")
    url: str = Field(..., title="the url of the property")
    is_active: bool = Field(..., title="the active status of the property")
    created_at: datetime = Field(..., title="the creation date of the property")
    updated_at: datetime = Field(..., title="the update date of the property")
    image_urls: Optional[List[str]] = Field(
        default_factory=list, title="the suumo image urls of the property"
    )

    @field_validator("url")
    def validate_url(cls, url):
        if not url.startswith("https://suumo.jp"):
            raise ValueError("url must start with https://suumo.jp")
        return url

    @model_validator(mode="after")
    def validate_timestamps(cls, model: "Property") -> "Property":
        if model.created_at and model.updated_at < model.created_at:
            raise ValueError("updated_at must be equal to or later than created_at")
        return model

    class Config:
        arbitrary_types_allowed = True
        json_schema_extra = {
            "example": {
                "name": "クレヴィア渋谷富ヶ谷",
                "url": "https://suumo.jp/ms/chuko/tokyo/sc_shibuya/nc_76483805/",
                "created_at": "2025-01-22T22:26:34.384Z",
                "updated_at": "2025-01-22T22:26:34.384Z",
            }
        }
