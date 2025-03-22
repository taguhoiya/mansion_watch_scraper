from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.id import PyObjectId


class Property(BaseModel):
    id: Optional[PyObjectId] = Field(
        default=None,
        alias="_id",
        description="Property ID",
    )
    name: str = Field(..., description="Property name")
    url: str = Field(..., description="Property listing URL")
    is_active: bool = Field(..., description="Whether the listing is currently active")
    large_property_description: Optional[str] = Field(
        None, description="High-level property features"
    )
    small_property_description: Optional[str] = Field(
        None,
        description="Detailed property description (HTML content is allowed)",
    )
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Record last update timestamp")
    image_urls: Optional[List[str]] = Field(
        default_factory=list, description="List of property image URLs"
    )

    @field_validator("url")
    def validate_url(cls, url: str) -> str:
        """Validate that the URL is from SUUMO."""
        if not url.startswith("https://suumo.jp"):
            raise ValueError("url must start with https://suumo.jp")
        return url

    @model_validator(mode="after")
    def validate_timestamps(cls, model: "Property") -> "Property":
        if model.created_at and model.updated_at < model.created_at:
            raise ValueError("updated_at must be equal to or later than created_at")
        return model

    def model_dump(self, *args, **kwargs):
        """Override model_dump to exclude id field."""
        kwargs["exclude"] = {"id", "_id", *kwargs.get("exclude", set())}
        return super().model_dump(*args, **kwargs)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_schema_extra": {
            "example": {
                "id": "679f48bb824469aa5fc15392",
                "name": "クレヴィア渋谷富ヶ谷",
                "url": "https://suumo.jp/ms/chuko/tokyo/sc_shibuya/nc_76483805/",
                "is_active": True,
                "large_property_description": "２沿線以上利用可、スーパー 徒歩10分以内、小学校 徒歩10分以内、駐輪場",
                "small_property_description": "◎戸建感覚を演出するメゾネット<br>◎スキップフロアのある、立体的な空間構成の2LDK<br>◎各洋室2面採光<br>◎屋上は開放感のあるルーフテラス<br>◎西森事務所によるデザイナーズ設計<br><br>♪駒場エリアには東京大学駒場キャンパスや公園等が点在しています。<br>豊かな自然に恵まれた地域で、春の新緑や秋の紅葉等、四季折々の風景を楽しめるエリアです。<br>♪京王井の頭線(駒場東大前駅)は渋谷駅・下北沢駅等へのアクセスも良好で、都心部への通勤通学、お出かけもしやすく利便性の高い駅。<br>♪近くの駒場東大前商店街では、朝市や夏祭り等の積極的なイベントが行われております。",
                "created_at": "2025-01-22T22:26:34.384Z",
                "updated_at": "2025-01-22T22:26:34.384Z",
                "image_urls": [
                    "https://storage.cloud.google.com/mansion_watch/1.jpg",
                    "https://storage.cloud.google.com/mansion_watch/2.jpg",
                ],
            }
        },
    }
