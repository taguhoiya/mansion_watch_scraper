# {
#     "_id": ObjectId("67b1fa375ad922a1c7ef808f"),
#     "filename": "989f85e5b3_75709932.jpg",
#     "metadata": {
#         "contentType": "image/jpeg",
#         "url": "https://suumo.jp/ms/chuko/tokyo/sc_meguro/nc_75709932/",
#     },
#     "chunkSize": 1048576,
#     "length": 35470,
#     "uploadDate": datetime.datetime(2025, 2, 16, 14, 46, 15, 511000),
# }

from datetime import datetime
from typing import Dict

from bson import ObjectId
from pydantic import BaseModel


class PropertyImage(BaseModel):
    _id: ObjectId
    filename: str
    metadata: Dict[str, str]
    chunkSize: int
    length: int
    uploadDate: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "_id": "67b1fa375ad922a1c7ef808f",
                "filename": "989f85e5b3_75709932.jpg",
                "metadata": {
                    "contentType": "image/jpeg",
                    "url": "https://suumo.jp/ms/chuko/tokyo/sc_meguro/nc_75709932/",
                },
                "chunkSize": 1048576,
                "length": 35470,
                "uploadDate": "2025-02-16T14:46:15.511Z",
            }
        }
