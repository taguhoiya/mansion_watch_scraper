from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.id import PyObjectId

# {
#     "_id": {"$oid": "6790f0aa68873b21a872d2a9"},
#     "所在地": "東京都目黒区駒場１",
#     "交通": [
#         "東京都目黒区駒場１",
#         "京王井の頭線「神泉」歩7分",
#         "京王井の頭線「駒場東大前」歩8分",
#         "ＪＲ山手線「渋谷」歩13分",
#     ],
#     "総戸数": "52戸",
#     "構造・階建て": "RC9階建",
#     "敷地面積": "-",
#     "敷地の権利形態": "所有権",
#     "用途地域": "-",
#     "駐車場": "空無",
#     "created_at": {"$date": "2025-01-22T22:20:42.788Z"},
#     "updated_at": {"$date": "2025-01-22T22:20:42.788Z"},
#     "property_id": {"$oid": "6790f0aa68873b21a872d2a7"},
# }


class CommonOverview(BaseModel):
    id: Optional[PyObjectId] = Field(
        alias="_id", default=None, title="the id of the common overview"
    )
    所在地: str = Field(..., title="the location of the property")
    交通: list[str] = Field(..., title="the transportation of the property")
    総戸数: str = Field(..., title="the total number of units")
    構造_階建て: str = Field(..., title="the structure and number of floors")
    敷地面積: str = Field(..., title="the site area")
    敷地の権利形態: str = Field(..., title="the site ownership form")
    用途地域: str = Field(..., title="the usage area")
    駐車場: str = Field(..., title="the parking lot")
    created_at: datetime = Field(..., title="the creation date of the common overview")
    updated_at: datetime = Field(..., title="the update date of the common overview")
    property_id: PyObjectId = Field(..., title="the id of the property")

    class Config:
        json_schema_extra = {
            "example": {
                "所在地": "東京都目黒区駒場１",
                "交通": [
                    "東京都目黒区駒場１",
                    "京王井の頭線「神泉」歩7分",
                    "京王井の頭線「駒場東大前」歩8分",
                    "ＪＲ山手線「渋谷」歩13分",
                ],
                "総戸数": "52戸",
                "構造_階建て": "RC9階建",
                "敷地面積": "-",
                "敷地の権利形態": "所有権",
                "用途地域": "-",
                "駐車場": "空無",
                "created_at": "2025-01-22T22:20:42.788Z",
                "updated_at": "2025-01-22T22:20:42.788Z",
                "property_id": "6790f0aa68873b21a872d2a7",
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
