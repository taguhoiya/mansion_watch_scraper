# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


import logging
import os
from typing import Dict, Union

import pymongo
from itemadapter import ItemAdapter

from app.models.common_overview import CommonOverview
from app.models.property import Property
from app.models.property_overview import PropertyOverview

properties = os.getenv("COLLECTION_PROPERTIES")
property_overviews = os.getenv("COLLECTION_PROPERTY_OVERVIEWS")
common_overviews = os.getenv("COLLECTION_COMMON_OVERVIEWS")


class MansionWatchScraperPipeline:
    def process_item(self, item, spider):
        return item


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
        self.client = pymongo.MongoClient(self.mongo_uri)
        self.db = self.client[self.mongo_db]

    def close_spider(self, spider):
        self.client.close()

    def process_item(
        self, item: Dict[str, Union[Property, PropertyOverview, CommonOverview]], spider
    ):
        if properties in item:
            if isinstance(item[properties], dict):
                result = self.db[properties].insert_one(
                    ItemAdapter(item[properties]).asdict()
                )
            else:
                self.logger.error(
                    f"Invalid type for properties: {type(item[properties])}"
                )
                raise TypeError(
                    f"Invalid type for properties: {type(item[properties])}"
                )
            property_id = result.inserted_id
        if property_overviews in item:
            if isinstance(item[property_overviews], dict):
                item[property_overviews]["property_id"] = property_id
                self.db[property_overviews].insert_one(
                    ItemAdapter(item[property_overviews]).asdict()
                )
            else:
                self.logger.error(
                    f"Invalid type for property_overviews: {type(item[property_overviews])}"
                )
                raise TypeError(
                    f"Invalid type for property_overviews: {type(item[property_overviews])}"
                )
        if common_overviews in item:
            if isinstance(item[common_overviews], dict):
                item[common_overviews]["property_id"] = property_id
                self.db[common_overviews].insert_one(
                    ItemAdapter(item[common_overviews]).asdict()
                )
            else:
                self.logger.error(
                    f"Invalid type for common_overviews: {type(item[common_overviews])}"
                )
                raise TypeError(
                    f"Invalid type for common_overviews: {type(item[common_overviews])}"
                )
        return item
