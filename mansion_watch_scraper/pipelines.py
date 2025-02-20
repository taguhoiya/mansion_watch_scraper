# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


import io
import logging
import os
import shutil
from typing import Dict, Union

import pymongo
import scrapy
from google.cloud import storage
from itemadapter import ItemAdapter
from PIL import Image
from pymongo.server_api import ServerApi
from scrapy.exceptions import DropItem
from scrapy.pipelines.images import ImagesPipeline

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
    def __init__(
        self, mongo_uri, mongo_db, images_store, gcp_bucket_name, gcp_folder_name
    ):
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db
        self.logger = logging.getLogger(__name__)
        self.images_store = images_store
        self.gcp_bucket_name = gcp_bucket_name
        self.folder_name = gcp_folder_name

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            mongo_uri=crawler.settings.get("MONGO_URI"),
            mongo_db=crawler.settings.get("MONGO_DATABASE"),
            images_store=crawler.settings.get("IMAGES_STORE"),
            gcp_bucket_name=crawler.settings.get("GCP_BUCKET_NAME"),
            gcp_folder_name=crawler.settings.get("GCP_FOLDER_NAME"),
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
    ) -> Dict:
        """
        Process items and store them in MongoDB.
        Handles different types of items and maintains relationships between them.
        """
        try:
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

        except Exception as e:
            self.logger.error(f"Error processing item: {e}")
            raise DropItem(f"Failed to process item: {e}")

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
                item[user_properties]["last_succeeded_at"] = get_current_time()
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


class SuumoImagesPipeline(ImagesPipeline):
    def open_spider(self, spider):
        super().open_spider(spider)
        self.logger = logging.getLogger(__name__)

        # Get the MongoDB client and database
        mongo_uri = spider.settings.get("MONGO_URI")
        mongo_db = spider.settings.get("MONGO_DATABASE")
        self.client = pymongo.MongoClient(mongo_uri)
        self.db = self.client[mongo_db]

        # Get the local directory where images are stored
        self.images_store = spider.settings.get("IMAGES_STORE")

        # Initialize the Google Cloud Storage client and bucket
        self.gcp_bucket_name = spider.settings.get("GCP_BUCKET_NAME")
        self.folder_name = spider.settings.get("GCP_FOLDER_NAME")
        self.storage_client = storage.Client()
        self.bucket = self.storage_client.bucket(self.gcp_bucket_name)

    def close_spider(self, spider):
        """Clean up resources when spider closes."""
        self.client.close()
        self.storage_client.close()

    def file_path(self, request, response=None, info=None, *, item=None):
        return request.url.split("/")[-1]

    def get_media_requests(self, item, info):
        """Get media requests for image downloads."""
        properties = item.get(os.getenv("COLLECTION_PROPERTIES"))
        if isinstance(properties, dict):
            image_urls = properties.get("image_urls", [])
        else:
            # Handle Pydantic model
            image_urls = getattr(properties, "image_urls", [])

        if not image_urls:
            self.logger.warning("No image URLs found in item")
            return []

        for image_url in image_urls:
            yield scrapy.Request(image_url)

    def _process_image(self, local_file):
        """Process and optimize the image for upload."""
        with Image.open(local_file) as img:
            if img.mode == "RGBA":
                img = img.convert("RGB")

            # Use a fixed quality setting for JPEG compression
            quality = int(os.getenv("GCS_IMAGE_QUALITY"))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            buffer.seek(0)  # Reset buffer position to beginning

            return buffer

    def _upload_to_gcs(self, local_file, destination_blob_name):
        """Upload the file to Google Cloud Storage."""
        blob = self.bucket.blob(destination_blob_name)

        try:
            # Process the image and get the buffer
            buffer = self._process_image(local_file)

            # Upload the processed buffer
            blob.upload_from_file(
                buffer, content_type="image/jpeg", rewind=True
            )  # Add rewind=True

            # Verify uploaded file size
            blob.reload()
            self.logger.info(f"Upload complete - GCS size: {blob.size/1024:.2f}KB")

            return True
        except Exception as e:
            self.logger.error(
                f"Failed to upload optimized image {destination_blob_name}: {e}"
            )
            return False

    def item_completed(self, results, item, info):
        """Handle completed item processing with proper cleanup and error handling."""
        try:
            # Gather successful image paths
            image_paths = [res["path"] for ok, res in results if ok]
            if not image_paths:
                raise DropItem("Item contains no images")

            # Process each image
            successful_uploads = []
            for image_path in image_paths:
                local_file = os.path.join(self.images_store, image_path)
                blob_path = f"{self.folder_name}/{image_path}"

                if self._upload_to_gcs(local_file, blob_path):
                    successful_uploads.append(image_path)
                else:
                    self.logger.warning(
                        f"Failed to upload optimized image: {blob_path}"
                    )

            # Clean up temporary files
            if os.path.isdir("tmp"):
                shutil.rmtree("tmp", ignore_errors=True)

            # Update item with successful uploads
            properties = item.get(os.getenv("COLLECTION_PROPERTIES"))
            if isinstance(properties, dict):
                properties.pop("image_urls", None)
                properties["image_urls"] = [
                    f"https://storage.cloud.google.com/{self.gcp_bucket_name}/{self.folder_name}/{path}"
                    for path in successful_uploads
                ]
            else:
                # Handle Pydantic model
                setattr(
                    properties,
                    "image_urls",
                    [
                        f"https://storage.cloud.google.com/{self.gcp_bucket_name}/{self.folder_name}/{path}"
                        for path in successful_uploads
                    ],
                )

            item[os.getenv("COLLECTION_PROPERTIES")] = properties
            adapter = ItemAdapter(item)
            adapter["image_paths"] = successful_uploads

            return item

        except Exception as e:
            self.logger.error(f"Error in item_completed: {e}")
            raise DropItem(f"Failed to process images: {e}")
