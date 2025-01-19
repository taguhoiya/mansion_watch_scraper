# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


import logging

import pymongo
from itemadapter import ItemAdapter


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

    def process_item(self, item, spider):
        self.logger.info(f"Processing item: {item}")

        if "properties" in item:
            self.db["properties"].insert_one(ItemAdapter(item["properties"]).asdict())
        if "property_overviews" in item:
            self.db["property_overviews"].insert_one(
                ItemAdapter(item["property_overviews"]).asdict()
            )
        if "common_overviews" in item:
            self.db["common_overviews"].insert_one(
                ItemAdapter(item["common_overviews"]).asdict()
            )
        return item
