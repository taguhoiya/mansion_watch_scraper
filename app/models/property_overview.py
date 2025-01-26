from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.id import PyObjectId

# {
#     "_id": {"$oid": "6790f0aa68873b21a872d2a8"},
#     "販売スケジュール": "-",
#     "イベント情報": "-",
#     "販売戸数": "1戸",
#     "最多価格帯": "-",
#     "価格": "7480万円",
#     "管理費": "1万8760円／月（委託(通勤)）",
#     "修繕積立金": "1万9320円／月",
#     "修繕積立基金": "-",
#     "諸費用": "-",
#     "間取り": "3DK+S（納戸）",
#     "専有面積": "74.17m",
#     "その他面積": "（壁芯）",
#     "引渡可能時期": "相談",
#     "完成時期(築年月)": "1969年7月",
#     "所在階": "5階",
#     "向き": "南東",
#     "エネルギー消費性能": "-",
#     "断熱性能": "-",
#     "目安光熱費": "-",
#     "リフォーム": "-",
#     "その他制限事項": "-",
#     "その他概要・特記事項": "担当者：神鳥 直人",
#     "created_at": {"$date": "2025-01-22T22:20:42.787Z"},
#     "updated_at": {"$date": "2025-01-22T22:20:42.787Z"},
#     "property_id": {"$oid": "6790f0aa68873b21a872d2a7"},
# }


class PropertyOverview(BaseModel):
    id: Optional[PyObjectId] = Field(
        alias="_id", default=None, title="the id of the property"
    )
    販売スケジュール: str = Field(..., title="the sales schedule of the property")
    イベント情報: str = Field(..., title="the event information of the property")
    販売戸数: str = Field(..., title="the number of units for sale")
    最多価格帯: str = Field(..., title="the highest price range")
    価格: str = Field(..., title="the price of the property")
    管理費: str = Field(..., title="the management fee of the property")
    修繕積立金: str = Field(..., title="the repair reserve fund of the property")
    修繕積立基金: str = Field(..., title="the repair reserve fund of the property")
    諸費用: str = Field(..., title="the other expenses of the property")
    間取り: str = Field(..., title="the floor plan of the property")
    専有面積: str = Field(..., title="the area of the property")
    その他面積: str = Field(
        ..., title="the other area of the property other than 占有面積"
    )
    引渡可能時期: str = Field(..., title="the rough delivery time of the property")
    # This field can be optional
    完成時期_築年月: Optional[str] = Field(
        None, title="the completion time of the property"
    )
    所在階: str = Field(..., title="the floor of the property")
    向き: str = Field(..., title="the direction of the property")
    エネルギー消費性能: str = Field(
        ..., title="the energy consumption performance of the property"
    )
    断熱性能: str = Field(..., title="the insulation performance of the property")
    目安光熱費: str = Field(
        ..., title="the estimated lighting and heating cost of the property"
    )
    リフォーム: str = Field(..., title="the renovation information of the property")
    # This field can be optional
    その他制限事項: Optional[str] = Field(
        None, title="the other restrictions of the property"
    )
    # This field can be optional\
    その他概要_特記事項: Optional[str] = Field(
        None, title="the other overview and special notes of the property"
    )
    created_at: datetime = Field(
        ..., title="the date and time the property was created"
    )
    updated_at: datetime = Field(
        ..., title="the date and time the property was last updated"
    )
    property_id: PyObjectId = Field(..., title="the id of the property")

    class Config:
        schema_extra = {
            "example": {
                "販売スケジュール": "-",
                "イベント情報": "-",
                "販売戸数": "1戸",
                "最多価格帯": "-",
                "価格": "7480万円",
                "管理費": "1万8760円／月（委託(通勤)）",
                "修繕積立金": "1万9320円／月",
                "修繕積立基金": "-",
                "諸費用": "-",
                "間取り": "3DK+S（納戸）",
                "専有面積": "74.17m",
                "その他面積": "（壁芯）",
                "引渡可能時期": "相談",
                "完成時期(築年月)": "1969年7月",
                "所在階": "5階",
                "向き": "南東",
                "エネルギー消費性能": "-",
                "断熱性能": "-",
                "目安光熱費": "-",
                "リフォーム": "-",
                "その他制限事項": "-",
                "その他概要・特記事項": "担当者：神鳥 直人",
                "created_at": "2025-01-22T22:20:42.787Z",
                "updated_at": "2025-01-22T22:20:42.787Z",
                "property_id": "6790f0aa68873b21a872d2a7",
            }
        }
