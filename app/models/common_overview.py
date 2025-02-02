from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.id import PyObjectId

# {
#     "_id": {"$oid": "679f4615b9e24a05799bf4b8"},
#     "location": "東京都目黒区駒場１",
#     "transportation": [
#         "東京都目黒区駒場１",
#         "京王井の頭線「駒場東大前」歩5分",
#         "東急田園都市線「池尻大橋」歩12分",
#     ],
#     "total_units": "6戸",
#     "structure_floors": "RC3階地下1階建",
#     "site_area": "-",
#     "site_ownership_type": "所有権",
#     "usage_area": "１種中高",
#     "parking_lot": "無",
#     "created_at": {"$date": "2025-02-02T19:16:53.123Z"},
#     "updated_at": {"$date": "2025-02-02T19:16:53.123Z"},
#     "property_id": {"$oid": "679f4615b9e24a05799bf4b6"},
# }


class CommonOverview(BaseModel):
    id: Optional[PyObjectId] = Field(
        alias="_id", default=None, title="the id of the common overview"
    )
    location: str = Field(..., title="the location of the common overview")
    transportation: list[str] = Field(
        ..., title="the transportation of the common overview"
    )
    total_units: str = Field(..., title="the total number of units")
    structure_floors: str = Field(..., title="the structure and number of floors")
    site_area: str = Field(..., title="the site area")
    site_ownership_type: str = Field(..., title="the site ownership type")
    usage_area: str = Field(..., title="the usage area")
    parking_lot: str = Field(..., title="the parking lot")
    created_at: datetime = Field(..., title="the creation date of the common overview")
    updated_at: datetime = Field(..., title="the update date of the common overview")
    property_id: PyObjectId = Field(..., title="the id of the property")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "679f4615b9e24a05799bf4b8",
                "location": "東京都目黒区駒場１",
                "transportation": [
                    "東京都目黒区駒場１",
                    "京王井の頭線「駒場東大前」歩5分",
                    "東急田園都市線「池尻大橋」歩12分",
                ],
                "total_units": "6戸",
                "structure_floors": "RC3階地下1階建",
                "site_area": "-",
                "site_ownership_type": "所有権",
                "usage_area": "１種中高",
                "parking_lot": "無",
                "created_at": "2025-02-02T19:16:53.123Z",
                "updated_at": "2025-02-02T19:16:53.123Z",
                "property_id": "679f4615b9e24a05799bf4b6",
            }
        }


COMMON_OVERVIEW_TRANSLATION_MAP = {
    "所在地": "location",
    "交通": "transportation",
    "総戸数": "total_units",
    "構造・階建て": "structure_floors",
    "敷地面積": "site_area",
    "敷地の権利形態": "site_ownership_type",
    "用途地域": "usage_area",
    "駐車場": "parking_lot",
}
