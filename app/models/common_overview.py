from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

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
        default=None,
        alias="_id",
        description="Common overview ID",
    )
    location: str = Field(..., description="Property location")
    transportation: List[str] = Field(
        ..., description="Available transportation options"
    )
    total_units: str = Field(..., description="Total number of units")
    structure_floors: str = Field(..., description="Structure and number of floors")
    site_area: str = Field(..., description="Site area")
    site_ownership_type: str = Field(..., description="Site ownership type")
    usage_area: str = Field(..., description="Usage area")
    parking_lot: str = Field(..., description="Parking lot availability")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Record last update timestamp")
    property_id: Optional[PyObjectId] = Field(
        default=None,
        description="Associated property ID",
    )

    @field_validator("property_id")
    def validate_object_id(cls, v):
        if v is None:
            return None
        return PyObjectId(v)

    @model_validator(mode="after")
    def validate_timestamps(cls, model: "CommonOverview") -> "CommonOverview":
        if model.created_at and model.updated_at < model.created_at:
            raise ValueError("updated_at must be equal to or later than created_at")
        return model

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_schema_extra": {
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
        },
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
