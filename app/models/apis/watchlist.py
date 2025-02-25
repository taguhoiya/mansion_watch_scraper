from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.id import PyObjectId

# [
#   {
#     "name": "ロクタス",
#     "url": "https://suumo.jp/ms/chuko/tokyo/sc_meguro/nc_75709932/",
#     "is_active": true,
#     "large_property_description": "２沿線以上利用可、スーパー 徒歩10分以内、小学校 徒歩10分以内、駐輪場",
#     "small_property_description": "◎戸建感覚を演出するメゾネット<br>◎スキップフロアのある、立体的な空間構成の2LDK<br>◎各洋室2面採光<br>◎屋上は開放感のあるルーフテラス<br>◎西森事務所によるデザイナーズ設計<br><br>♪駒場エリアには東京大学駒場キャンパスや公園等が点在しています。<br>豊かな自然に恵まれた地域で、春の新緑や秋の紅葉等、四季折々の風景を楽しめるエリアです。<br>♪京王井の頭線(駒場東大前駅)は渋谷駅・下北沢駅等へのアクセスも良好で、都心部への通勤通学、お出かけもしやすく利便性の高い駅。<br>♪近くの駒場東大前商店街では、朝市や夏祭り等の積極的なイベントが行われております。",
#     "created_at": "2025-02-24T20:21:37.683000",
#     "updated_at": "2025-02-24T20:21:37.683000",
#     "image_urls": [
#       "https://storage.cloud.google.com/mansion_watch/1.jpg",
#       "https://storage.cloud.google.com/mansion_watch/2.jpg",
#     ],
#     "price": "1億4700万円",
#     "floor_plan": "2LDK",
#     "completion_time": "2009年12月",
#     "area": "92.36m",
#     "other_area": "（27.93坪）（壁芯）",
#     "location": "東京都目黒区駒場１",
#     "transportation": [
#       "京王井の頭線「駒場東大前」歩5分",
#       "東急田園都市線「池尻大橋」歩12分"
#     ]
#   }
# ]


class UserWatchlist(BaseModel):
    """
    Represents a user's property watchlist item with detailed property information.
    """

    id: PyObjectId = Field(alias="_id", description="Property ID")
    name: str = Field(..., description="Property name")
    url: str = Field(..., description="Property listing URL")
    is_active: bool = Field(..., description="Whether the listing is currently active")

    # Property details
    large_property_description: Optional[str] = Field(
        None, description="High-level property features"
    )
    small_property_description: Optional[str] = Field(
        None, description="Detailed property description"
    )
    image_urls: Optional[List[str]] = Field(
        default_factory=list, description="List of property image URLs"
    )

    # Required property details
    price: str = Field(..., description="Property price in Japanese Yen")
    floor_plan: str = Field(..., description="Floor plan type (e.g., 2LDK)")
    completion_time: str = Field(..., description="Property completion date")
    area: str = Field(..., description="Property area in square meters")
    other_area: str = Field(..., description="Additional area information")
    location: str = Field(..., description="Property location")
    transportation: List[str] = Field(
        ..., description="Available transportation options"
    )

    # Timestamps
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Record last update timestamp")

    @field_validator("url")
    def validate_url(cls, url: str) -> str:
        """Validate that the URL is from SUUMO."""
        if not url.startswith("https://suumo.jp"):
            raise ValueError("URL must start with https://suumo.jp")
        return url

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_schema_extra": {
            "example": {
                "name": "ロクタス",
                "url": "https://suumo.jp/ms/chuko/tokyo/sc_meguro/nc_75709932/",
                "is_active": True,
                "large_property_description": "２沿線以上利用可、スーパー 徒歩10分以内、小学校 徒歩10分以内、駐輪場",
                "small_property_description": (
                    "◎戸建感覚を演出するメゾネット<br>"
                    "◎スキップフロアのある、立体的な空間構成の2LDK<br>"
                    "◎各洋室2面採光<br>"
                    "◎屋上は開放感のあるルーフテラス<br>"
                    "◎西森事務所によるデザイナーズ設計"
                ),
                "image_urls": [
                    "https://storage.cloud.google.com/mansion_watch/1.jpg",
                    "https://storage.cloud.google.com/mansion_watch/2.jpg",
                ],
                "price": "1億4700万円",
                "floor_plan": "2LDK",
                "completion_time": "2009年12月",
                "area": "92.36m",
                "other_area": "（27.93坪）（壁芯）",
                "location": "東京都目黒区駒場１",
                "transportation": [
                    "京王井の頭線「駒場東大前」歩5分",
                    "東急田園都市線「池尻大橋」歩12分",
                ],
                "created_at": "2025-02-24T20:21:37.683000",
                "updated_at": "2025-02-24T20:21:37.683000",
            }
        },
    }
