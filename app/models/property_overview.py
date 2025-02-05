from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.id import PyObjectId

# {
#     "_id": {"$oid": "679f48bb824469aa5fc15392"},
#     "sales_schedule": "-",
#     "event_information": "-",
#     "number_of_units_for_sale": "1戸",
#     "highest_price_range": "-",
#     "price": "1億4700万円",
#     "maintenance_fee": "8906円／月（自主管理(管理員なし)）",
#     "repair_reserve_fund": "2万4618円／月",
#     "first_repair_reserve_fund": "-",
#     "other_expenses": "-",
#     "floor_plan": "2LDK",
#     "area": "92.36m",
#     "other_area": "（27.93坪）（壁芯）",
#     "delivery_time": "相談",
#     "completion_time": "2009年12月",
#     "floor": "2階",
#     "direction": "北",
#     "energy_consumption_performance": "-",
#     "insulation_performance": "-",
#     "estimated_utility_cost": "-",
#     "renovation": "-",
#     "other_restrictions": "※所在階：2階・3階 ※上記バルコニー向きはルーフテラスの向きになります。 ●ルーフテラス面積／約40.31平米（約12.19坪）：使用料無償 （上記ルーフテラス面積については計画概要に基づく面積です。） ●専用駐輪場／有：使用料無償（令和6年5月11日現在） ●ペットの飼育については別途ペット使用細則を遵守していただきます。 ●間取図の畳数表記（J）は1畳＝1.62平米で換算した約表示です。 ●略号凡例：Sto.／収納、R／冷蔵庫置場",
#     "other_overview_and_special_notes": "担当者：大野博史",
#     "created_at": {"$date": "2025-02-02T19:28:11.628Z"},
#     "updated_at": {"$date": "2025-02-02T19:28:11.628Z"},
#     "property_id": {"$oid": "679f48bb824469aa5fc15391"},
# }


class PropertyOverview(BaseModel):
    id: Optional[PyObjectId] = Field(
        alias="_id", default=None, title="the id of the property"
    )
    sales_schedule: str = Field(..., title="the sales schedule")
    event_information: str = Field(..., title="the event information")
    number_of_units_for_sale: str = Field(..., title="the number of units for sale")
    highest_price_range: str = Field(..., title="the highest price range")
    price: str = Field(..., title="the price")
    maintenance_fee: str = Field(..., title="the maintenance fee")
    repair_reserve_fund: str = Field(..., title="the repair reserve fund")
    first_repair_reserve_fund: str = Field(..., title="the first repair reserve fund")
    other_expenses: str = Field(..., title="the other expenses")
    floor_plan: str = Field(..., title="the floor plan")
    area: str = Field(..., title="the area")
    other_area: str = Field(..., title="the other area")
    delivery_time: str = Field(..., title="the delivery time")
    completion_time: str = Field(..., title="the completion time")
    floor: str = Field(..., title="the floor")
    direction: str = Field(..., title="the direction")
    energy_consumption_performance: str = Field(
        ..., title="the energy consumption performance"
    )
    insulation_performance: str = Field(..., title="the insulation performance")
    estimated_utility_cost: str = Field(..., title="the estimated utility cost")
    renovation: str = Field(..., title="the renovation")
    other_restrictions: str = Field(..., title="the other restrictions")
    other_overview_and_special_notes: str = Field(
        ..., title="the other overview and special notes"
    )
    created_at: datetime = Field(
        ..., title="the date and time the property was created"
    )
    updated_at: datetime = Field(
        ..., title="the date and time the property was last updated"
    )
    property_id: PyObjectId = Field(..., title="the id of the property")

    @field_validator("id", "property_id")
    def validate_object_id(cls, v):
        return PyObjectId(v)

    @field_validator("created_at", "updated_at")
    def validate_timestamps(cls, created_at, updated_at):
        if created_at and updated_at < created_at:
            raise ValueError("updated_at must be equal to or later than created_at")
        return updated_at

    class Config:
        json_schema_extra = {
            "example": {
                "id": "679f48bb824469aa5fc15392",
                "sales_schedule": "-",
                "event_information": "-",
                "number_of_units_for_sale": "1戸",
                "highest_price_range": "-",
                "price": "1億4700万円",
                "maintenance_fee": "8906円／月（自主管理(管理員なし)）",
                "repair_reserve_fund": "2万4618円／月",
                "first_repair_reserve_fund": "-",
                "other_expenses": "-",
                "floor_plan": "2LDK",
                "area": "92.36m",
                "other_area": "（27.93坪）（壁芯）",
                "delivery_time": "相談",
                "completion_time": "2009年12月",
                "floor": "2階",
                "direction": "北",
                "energy_consumption_performance": "-",
                "insulation_performance": "-",
                "estimated_utility_cost": "-",
                "renovation": "-",
                "other_restrictions": "※所在階：2階・3階 ※上記バルコニー向きはルーフテラスの向きになります。 ●ルーフテラス面積／約40.31平米（約12.19坪）：使用料無償 （上記ルーフテラス面積については計画概要に基づく面積です。） ●専用駐輪場／有：使用料無償（令和6年5月11日現在） ●ペットの飼育については別途ペット使用細則を遵守していただきます。 ●間取図の畳数表記（J）は1畳＝1.62平米で換算した約表示です。 ●略号凡例：Sto.／収納、R／冷蔵庫置場",
                "other_overview_and_special_notes": "担当者：大野博史",
                "created_at": "2025-02-02T19:28:11.628Z",
            }
        }


# The difference between 修繕積立金 and 修繕積立基金 is explained in https://suumo.jp/article/oyakudachi/oyaku/ms_shinchiku/ms_money/ms_shuzentsumitatekikin/
# 修繕積立金: 建物の外壁やエントランス、屋上などの共用部分を維持し、修繕するために行われる「大規模修繕」などに必要な資金
# 修繕積立基金: 第一回の大規模修繕工事に充てるためのお金
PROPERTY_OVERVIEW_TRANSLATION_MAP = {
    "販売スケジュール": "sales_schedule",
    "イベント情報": "event_information",
    "販売戸数": "number_of_units_for_sale",
    "最多価格帯": "highest_price_range",
    "価格": "price",
    "管理費": "maintenance_fee",
    "修繕積立金": "repair_reserve_fund",
    "修繕積立基金": "first_repair_reserve_fund",
    "諸費用": "other_expenses",
    "間取り": "floor_plan",
    "専有面積": "area",
    "その他面積": "other_area",
    "引渡可能時期": "delivery_time",
    "完成時期(築年月)": "completion_time",
    "所在階": "floor",
    "向き": "direction",
    "エネルギー消費性能": "energy_consumption_performance",
    "断熱性能": "insulation_performance",
    "目安光熱費": "estimated_utility_cost",
    "リフォーム": "renovation",
    "その他制限事項": "other_restrictions",
    "その他概要・特記事項": "other_overview_and_special_notes",
}
