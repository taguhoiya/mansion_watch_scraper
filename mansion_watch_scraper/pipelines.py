# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


import logging
import os
from typing import Dict, Union

import pymongo
from itemadapter import ItemAdapter
from pymongo.server_api import ServerApi

from app.models.common_overview import CommonOverview
from app.models.property import Property
from app.models.property_overview import PropertyOverview
from app.models.user_property import UserProperty
from app.services.dates import get_current_time

properties = os.getenv("COLLECTION_PROPERTIES")
user_properties = os.getenv("COLLECTION_USER_PROPERTIES")
property_overviews = os.getenv("COLLECTION_PROPERTY_OVERVIEWS")
common_overviews = os.getenv("COLLECTION_COMMON_OVERVIEWS")


class MongoPipeline:
    def __init__(self, mongo_uri, mongo_db):
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db
        self.logger = logging.getLogger(__name__)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            mongo_uri=crawler.settings.get("MONGO_URI"),
            mongo_db=crawler.settings.get("MONGO_DATABASE"),
        )

    def open_spider(self, spider):
        self.logger.info("Opening MongoDB connection")
        self.client = pymongo.MongoClient(self.mongo_uri, server_api=ServerApi("1"))
        self.db = self.client[self.mongo_db]

    def close_spider(self, spider):
        self.client.close()

    def process_item(
        self,
        item: Dict[
            str, Union[Property, UserProperty, PropertyOverview, CommonOverview]
        ],
        spider,
    ):
        property_id = None

        if properties in item:
            property_id = self.process_properties(item)

        if user_properties in item:
            self.process_user_properties(item, property_id)

        if property_overviews in item:
            self.process_property_overviews(item, property_id)

        if common_overviews in item:
            self.process_common_overviews(item, property_id)

        return item

    def process_properties(self, item):
        if isinstance(item[properties], dict):
            url = item[properties]["url"]
            coll = self.db[properties]

            # Check if the property already exists
            property = coll.find_one({"url": url})
            if property:
                # Remove created_at field to avoid updating it
                item[properties].pop("created_at", None)
                result = coll.update_one(
                    {"created_at": property["created_at"]},
                    {"$set": item[properties]},
                )
                property_id = property["_id"]

                self.logger.info(f"Property ID: {property_id}")
            else:
                result = coll.insert_one(ItemAdapter(item[properties]).asdict())
                property_id = result.inserted_id

        else:
            self.logger.error(f"Invalid type for properties: {type(item[properties])}")
            raise TypeError(f"Invalid type for properties: {type(item[properties])}")
        return property_id

    def process_user_properties(self, item, property_id):
        if isinstance(item[user_properties], dict):
            item[user_properties]["property_id"] = property_id
            line_user_id = item[user_properties]["line_user_id"]
            coll = self.db[user_properties]

            # Check if the user already has a property
            user_property = coll.find_one(
                {"line_user_id": line_user_id, "property_id": property_id}
            )
            if user_property:
                # Remove first_succeeded_at and last_succeeded_at fields to avoid updating them
                item[user_properties].pop("first_succeeded_at", None)
                item[user_properties].pop("last_succeeded_at", None)
                coll.update_one(
                    {"first_succeeded_at": user_property["first_succeeded_at"]},
                    {
                        "$set": {
                            "last_succeeded_at": get_current_time(),
                            **item[user_properties],
                        }
                    },
                )
            else:
                coll.insert_one(ItemAdapter(item[user_properties]).asdict())

        else:
            self.logger.error(
                f"Invalid type for user_properties: {type(item[user_properties])}"
            )
            raise TypeError(
                f"Invalid type for user_properties: {type(item[user_properties])}"
            )

    def process_property_overviews(self, item, property_id):
        if isinstance(item[property_overviews], dict):
            item[property_overviews]["property_id"] = property_id
            coll = self.db[property_overviews]

            # Check if the property overview already exists
            property_overview = coll.find_one({"property_id": property_id})
            if property_overview:
                # Remove created_at field to avoid updating it
                item[property_overviews].pop("created_at", None)
                coll.update_one(
                    {"created_at": property_overview["created_at"]},
                    {"$set": item[property_overviews]},
                )
            else:
                coll.insert_one(ItemAdapter(item[property_overviews]).asdict())

        else:
            self.logger.error(
                f"Invalid type for property_overviews: {type(item[property_overviews])}"
            )
            raise TypeError(
                f"Invalid type for property_overviews: {type(item[property_overviews])}"
            )

    def process_common_overviews(self, item, property_id):
        logging.info(isinstance(item[common_overviews], dict))
        if isinstance(item[common_overviews], dict):
            item[common_overviews]["property_id"] = property_id
            coll = self.db[common_overviews]
            # Check if the common overview already exists
            common_overview = coll.find_one({"property_id": property_id})
            if common_overview:
                # Remove created_at field to avoid updating it
                item[common_overviews].pop("created_at", None)
                coll.update_one(
                    {"created_at": common_overview["created_at"]},
                    {"$set": item[common_overviews]},
                )
            else:
                coll.insert_one(ItemAdapter(item[common_overviews]).asdict())
        else:
            self.logger.error(
                f"Invalid type for common_overviews: {type(item[common_overviews])}"
            )
            raise TypeError(
                f"Invalid type for common_overviews: {type(item[common_overviews])}"
            )
