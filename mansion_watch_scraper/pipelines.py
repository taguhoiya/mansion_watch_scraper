"""
Scrapy pipelines for processing and storing scraped data.

This module contains pipelines for:
1. Storing data in MongoDB
2. Processing and uploading images to Google Cloud Storage
"""

import io
import logging
import os
import shutil
from typing import Any, Dict, Optional, Tuple, TypeVar, Union

import pymongo
import scrapy
from bson import ObjectId
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

# Environment variables for collection names
PROPERTIES = os.getenv("COLLECTION_PROPERTIES")
USER_PROPERTIES = os.getenv("COLLECTION_USER_PROPERTIES")
PROPERTY_OVERVIEWS = os.getenv("COLLECTION_PROPERTY_OVERVIEWS")
COMMON_OVERVIEWS = os.getenv("COLLECTION_COMMON_OVERVIEWS")

# Type definitions
T = TypeVar("T")
ItemType = Dict[str, Union[Property, UserProperty, PropertyOverview, CommonOverview]]
MongoResult = Tuple[bool, Optional[ObjectId]]

# Setup logger
logger = logging.getLogger(__name__)


def convert_to_dict(obj: Any, collection_name: str) -> Dict[str, Any]:
    """
    Convert Pydantic model or dictionary to MongoDB-compatible dictionary.

    Args:
        obj: Object to convert (Pydantic model or dict)
        collection_name: Name of the collection for logging purposes

    Returns:
        Dictionary representation of the object
    """
    if isinstance(obj, Property):
        # Exclude id field for Property objects
        return obj.model_dump(exclude={"id"}, by_alias=True)
    elif hasattr(obj, "model_dump"):
        # For other Pydantic models
        return obj.model_dump(by_alias=True)
    elif isinstance(obj, dict):
        return obj
    else:
        logger.error(f"Unexpected object type in {collection_name}: {type(obj)}")
        return {}


def ensure_object_id(value: Any) -> Optional[ObjectId]:
    """
    Ensure a value is an ObjectId.

    Args:
        value: Value to convert to ObjectId

    Returns:
        ObjectId instance or None if conversion fails
    """
    if value is None:
        return None

    if isinstance(value, ObjectId):
        return value

    try:
        return ObjectId(value)
    except Exception as e:
        logger.error(f"Failed to convert value to ObjectId: {e}")
        return None


def process_property(
    db: pymongo.MongoClient, item: Dict[str, Any]
) -> Optional[ObjectId]:
    """
    Process property data and store in MongoDB.

    Args:
        db: MongoDB database connection
        item: Item containing property data

    Returns:
        ObjectId of the property document or None if processing fails
    """
    if PROPERTIES not in item:
        return None

    property_dict = convert_to_dict(item[PROPERTIES], "properties")

    # Remove _id field if it's None to avoid duplicate key error
    if "_id" in property_dict and property_dict["_id"] is None:
        property_dict.pop("_id")

    query = {"url": property_dict["url"]}
    existing = db[PROPERTIES].find_one(query)

    if existing:
        # Update existing document
        # Remove fields that shouldn't be updated
        for field in ["_id", "created_at"]:
            property_dict.pop(field, None)
        db[PROPERTIES].update_one(query, {"$set": property_dict})
        return existing["_id"]
    else:
        # Insert new document
        result = db[PROPERTIES].insert_one(property_dict)
        return result.inserted_id


def process_user_property(
    db: pymongo.MongoClient, item: Dict[str, Any], property_id: ObjectId
) -> Optional[ObjectId]:
    """
    Process user property data and store in MongoDB.

    Args:
        db: MongoDB database connection
        item: Item containing user property data
        property_id: ObjectId of the associated property

    Returns:
        ObjectId of the user property document or None if processing fails
    """
    if USER_PROPERTIES not in item:
        return None

    user_property_dict = convert_to_dict(item[USER_PROPERTIES], "user_properties")

    # Add property_id to the dictionary
    user_property_dict["property_id"] = property_id

    # Create the UserProperty object with the property_id
    user_property_obj = UserProperty(**user_property_dict)

    # Convert back to dict for MongoDB operations
    user_property_dict = convert_to_dict(user_property_obj, "user_properties")

    # Remove _id field if it's None to avoid duplicate key error
    if "_id" in user_property_dict and user_property_dict["_id"] is None:
        user_property_dict.pop("_id")

    # Ensure property_id is stored as an ObjectId
    if "property_id" in user_property_dict:
        user_property_dict["property_id"] = ensure_object_id(
            user_property_dict["property_id"]
        )

    query = {
        "line_user_id": user_property_dict["line_user_id"],
        "property_id": property_id,
    }

    existing = db[USER_PROPERTIES].find_one(query)
    if existing:
        # Update existing document
        update_data = {
            **user_property_dict,
            "last_succeeded_at": get_current_time(),
        }
        # Remove fields that shouldn't be updated
        for field in ["_id", "first_succeeded_at", "created_at"]:
            update_data.pop(field, None)

        db[USER_PROPERTIES].update_one(query, {"$set": update_data})
        return existing["_id"]
    else:
        # Insert new document with timestamps
        user_property_dict.update(
            {
                "last_succeeded_at": get_current_time(),
                "first_succeeded_at": get_current_time(),
            }
        )
        result = db[USER_PROPERTIES].insert_one(user_property_dict)
        return result.inserted_id


def process_property_overview(
    db: pymongo.MongoClient, item: Dict[str, Any], property_id: ObjectId
) -> Optional[ObjectId]:
    """
    Process property overview data and store in MongoDB.

    Args:
        db: MongoDB database connection
        item: Item containing property overview data
        property_id: ObjectId of the associated property

    Returns:
        ObjectId of the property overview document or None if processing fails
    """
    if PROPERTY_OVERVIEWS not in item:
        return None

    # Set property_id on the PropertyOverview object
    item[PROPERTY_OVERVIEWS].property_id = property_id

    # Convert to dict for MongoDB operations
    overview_dict = convert_to_dict(item[PROPERTY_OVERVIEWS], "property_overviews")

    # Remove _id field if it's None to avoid duplicate key error
    if "_id" in overview_dict and overview_dict["_id"] is None:
        overview_dict.pop("_id")

    # Ensure property_id is stored as an ObjectId
    if "property_id" in overview_dict:
        overview_dict["property_id"] = ensure_object_id(overview_dict["property_id"])

    query = {"property_id": property_id}
    existing = db[PROPERTY_OVERVIEWS].find_one(query)

    if existing:
        # Update existing document
        # Remove fields that shouldn't be updated
        for field in ["_id", "created_at"]:
            overview_dict.pop(field, None)
        db[PROPERTY_OVERVIEWS].update_one(query, {"$set": overview_dict})
        return existing["_id"]
    else:
        # Insert new document
        result = db[PROPERTY_OVERVIEWS].insert_one(overview_dict)
        return result.inserted_id


def process_common_overview(
    db: pymongo.MongoClient, item: Dict[str, Any], property_id: ObjectId
) -> Optional[ObjectId]:
    """
    Process common overview data and store in MongoDB.

    Args:
        db: MongoDB database connection
        item: Item containing common overview data
        property_id: ObjectId of the associated property

    Returns:
        ObjectId of the common overview document or None if processing fails
    """
    if COMMON_OVERVIEWS not in item:
        return None

    # Set property_id on the CommonOverview object
    item[COMMON_OVERVIEWS].property_id = property_id

    # Convert to dict for MongoDB operations
    overview_dict = convert_to_dict(item[COMMON_OVERVIEWS], "common_overviews")

    # Remove _id field if it's None to avoid duplicate key error
    if "_id" in overview_dict and overview_dict["_id"] is None:
        overview_dict.pop("_id")

    # Ensure property_id is stored as an ObjectId
    if "property_id" in overview_dict:
        overview_dict["property_id"] = ensure_object_id(overview_dict["property_id"])

    query = {"property_id": property_id}
    existing = db[COMMON_OVERVIEWS].find_one(query)

    if existing:
        # Update existing document
        # Remove fields that shouldn't be updated
        for field in ["_id", "created_at"]:
            overview_dict.pop(field, None)
        db[COMMON_OVERVIEWS].update_one(query, {"$set": overview_dict})
        return existing["_id"]
    else:
        # Insert new document
        result = db[COMMON_OVERVIEWS].insert_one(overview_dict)
        return result.inserted_id


class MongoPipeline:
    """Pipeline for storing scraped data in MongoDB."""

    def __init__(
        self,
        mongo_uri: str,
        mongo_db: str,
        images_store: str,
        gcp_bucket_name: str,
        gcp_folder_name: str,
    ):
        """
        Initialize the MongoDB pipeline.

        Args:
            mongo_uri: MongoDB connection URI
            mongo_db: MongoDB database name
            images_store: Local directory to store images
            gcp_bucket_name: Google Cloud Storage bucket name
            gcp_folder_name: Google Cloud Storage folder name
        """
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db
        self.images_store = images_store
        self.gcp_bucket_name = gcp_bucket_name
        self.folder_name = gcp_folder_name
        self.logger = logging.getLogger(__name__)
        self.client = None
        self.db = None

    @classmethod
    def from_crawler(cls, crawler):
        """
        Create pipeline instance from crawler.

        Args:
            crawler: Scrapy crawler

        Returns:
            MongoPipeline instance
        """
        return cls(
            mongo_uri=crawler.settings.get("MONGO_URI"),
            mongo_db=crawler.settings.get("MONGO_DATABASE"),
            images_store=crawler.settings.get("IMAGES_STORE"),
            gcp_bucket_name=crawler.settings.get("GCP_BUCKET_NAME"),
            gcp_folder_name=crawler.settings.get("GCP_FOLDER_NAME"),
        )

    def open_spider(self, spider):
        """
        Initialize MongoDB connection when spider opens.

        Args:
            spider: Scrapy spider
        """
        self.logger.info("Opening MongoDB connection")
        self.client = pymongo.MongoClient(self.mongo_uri, server_api=ServerApi("1"))
        self.db = self.client[self.mongo_db]

    def close_spider(self, spider):
        """
        Close MongoDB connection when spider closes.

        Args:
            spider: Scrapy spider
        """
        if self.client:
            self.client.close()
        self.logger.info("Completed MongoPipeline")

    def process_item(self, item: ItemType, spider) -> ItemType:
        """
        Process items and store them in MongoDB.

        Args:
            item: Scraped item
            spider: Scrapy spider

        Returns:
            Processed item

        Raises:
            DropItem: If item processing fails
        """
        try:
            # First insert/update property and get its ID
            property_id = process_property(self.db, item)

            if not property_id:
                return item

            # Process remaining items with property_id
            processors = [
                (USER_PROPERTIES, process_user_property),
                (PROPERTY_OVERVIEWS, process_property_overview),
                (COMMON_OVERVIEWS, process_common_overview),
            ]

            for collection_name, processor_func in processors:
                if collection_name in item:
                    processor_func(self.db, item, property_id)

            return item

        except Exception as e:
            self.logger.error(f"Error processing item: {e}")
            raise DropItem(f"Failed to process item: {e}")


def process_image(image_file: str) -> io.BytesIO:
    """
    Process and optimize an image for upload.

    Args:
        image_file: Path to the image file

    Returns:
        BytesIO buffer containing the processed image
    """
    with Image.open(image_file) as img:
        if img.mode == "RGBA":
            img = img.convert("RGB")

        # Use a fixed quality setting for JPEG compression
        quality = int(os.getenv("GCS_IMAGE_QUALITY", "85"))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        buffer.seek(0)  # Reset buffer position to beginning

        return buffer


def upload_to_gcs(
    bucket: storage.bucket.Bucket, local_file: str, destination_blob_name: str
) -> bool:
    """
    Upload a file to Google Cloud Storage.

    Args:
        bucket: GCS bucket
        local_file: Path to local file
        destination_blob_name: Destination blob name in GCS

    Returns:
        True if upload successful, False otherwise
    """
    blob = bucket.blob(destination_blob_name)

    try:
        # Process the image and get the buffer
        buffer = process_image(local_file)

        # Upload the processed buffer
        blob.upload_from_file(buffer, content_type="image/jpeg", rewind=True)

        # Verify uploaded file
        blob.reload()
        return True

    except Exception as e:
        logger.error(f"Failed to upload image {destination_blob_name}: {e}")
        return False


class SuumoImagesPipeline(ImagesPipeline):
    """Pipeline for downloading, processing, and uploading images to Google Cloud Storage."""

    def open_spider(self, spider):
        """
        Initialize resources when spider opens.

        Args:
            spider: Scrapy spider
        """
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
        """
        Clean up resources when spider closes.

        Args:
            spider: Scrapy spider
        """
        if self.client:
            self.client.close()
        if self.storage_client:
            self.storage_client.close()
        self.logger.info("Completed SuumoImagesPipeline")

    def file_path(self, request, response=None, info=None, *, item=None):
        """
        Determine file path for downloaded image.

        Args:
            request: Scrapy request
            response: Scrapy response
            info: Pipeline info
            item: Scraped item

        Returns:
            File path for the image
        """
        return request.url.split("/")[-1]

    def get_media_requests(self, item, info):
        """
        Get media requests for image downloads.

        Args:
            item: Scraped item
            info: Pipeline info

        Returns:
            Iterator of Scrapy requests
        """
        properties = item.get(PROPERTIES)

        if not properties:
            self.logger.warning("No properties found in item")
            return []

        image_urls = properties.image_urls if hasattr(properties, "image_urls") else []

        if not image_urls:
            self.logger.warning("No image URLs found in item")
            return []

        for image_url in image_urls:
            yield scrapy.Request(image_url)

    def item_completed(self, results, item, info):
        """
        Handle completed item processing with proper cleanup and error handling.

        Args:
            results: Results from image downloads
            item: Scraped item
            info: Pipeline info

        Returns:
            Processed item

        Raises:
            DropItem: If item processing fails
        """
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

                if upload_to_gcs(self.bucket, local_file, blob_path):
                    successful_uploads.append(image_path)
                else:
                    self.logger.warning(f"Failed to upload image: {blob_path}")

            # Clean up temporary files
            if os.path.isdir("tmp"):
                shutil.rmtree("tmp", ignore_errors=True)

            # Update item with successful uploads
            properties = item.get(PROPERTIES)

            if not properties:
                return item

            gcs_urls = [
                f"https://storage.cloud.google.com/{self.gcp_bucket_name}/{self.folder_name}/{path}"
                for path in successful_uploads
            ]

            if isinstance(properties, dict):
                properties.pop("image_urls", None)
                properties["image_urls"] = gcs_urls
            else:
                # Handle Pydantic model
                setattr(properties, "image_urls", gcs_urls)

            item[PROPERTIES] = properties
            adapter = ItemAdapter(item)
            adapter["image_paths"] = successful_uploads

            return item

        except Exception as e:
            self.logger.error(f"Error in item_completed: {e}")
            raise DropItem(f"Failed to process images: {e}")
