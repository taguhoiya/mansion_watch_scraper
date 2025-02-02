from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.id import PyObjectId

# {
#     "_id": {"$oid": "6790f20a4dffe24d21125ae6"},
#     "property_name": "クレヴィア渋谷富ヶ谷",
#     "url": "https://suumo.jp/ms/chuko/tokyo/sc_shibuya/nc_76483805/",
#     "created_at": {"$date": "2025-01-22T22:26:34.384Z"},
#     "updated_at": {"$date": "2025-01-22T22:26:34.384Z"},
# }


class Property(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    name: str = Field(..., title="the name of the property")
    url: str = Field(..., title="the url of the property")
    created_at: datetime = Field(..., title="the creation date of the property")
    updated_at: datetime = Field(..., title="the update date of the property")

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
