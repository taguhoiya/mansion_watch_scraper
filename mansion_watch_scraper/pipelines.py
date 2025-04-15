"""
Scrapy pipelines for processing and storing scraped data.

This module contains pipelines for:
1. Storing data in MongoDB
2. Processing and uploading images to Google Cloud Storage
"""

import hashlib
import io
import logging
import os
import re
import tempfile
import time
import urllib.parse
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple, TypeVar, Union

import pymongo
import requests
from bson import ObjectId
from google.cloud import storage
from PIL import Image
from pymongo.server_api import ServerApi
from scrapy.exceptions import DropItem
from scrapy.http import Request
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
MongoDocument = Optional[Dict[str, Any]]

# Setup logger
logger = logging.getLogger(__name__)


@dataclass
class ImageRequest:
    """Configuration for image download requests."""

    url: str
    headers: Dict[str, str]
    timeout: int = 30


@dataclass
class ProcessedImage:
    """Result of image processing."""

    path: str
    url: str
    content_type: str
    size: tuple[int, int]


def create_image_request(url: str) -> ImageRequest:
    """Create a standardized image request configuration."""
    return ImageRequest(
        url=url, headers={"Accept": "image/*", "Referer": "https://suumo.jp/"}
    )


def validate_response(response: requests.Response) -> None:
    """Validate HTTP response for image downloads."""
    if response.status_code != 200:
        raise ValueError(f"Invalid response status: {response.status_code}")
    if not response.headers.get("Content-Type", "").startswith("image/"):
        raise ValueError("Invalid content type")


def process_image_file(file_path: str) -> tuple[int, int]:
    """Process and validate image file."""
    with Image.open(file_path) as img:
        if img.mode != "RGB":
            img = img.convert("RGB")
            img.save(file_path, format="JPEG", quality=95)

        if min(img.size) < 50:
            raise ValueError(f"Image too small: {img.size}")
        return img.size


def download_image(
    request: ImageRequest, tmp_dir: str, max_retries: int = 3
) -> Optional[ProcessedImage]:
    """Download and process a single image with retry logic."""
    for attempt in range(max_retries):
        try:
            with requests.Session() as session:
                session.headers.update(request.headers)
                response = session.get(request.url, timeout=request.timeout)
                validate_response(response)

                with tempfile.NamedTemporaryFile(
                    delete=False, dir=tmp_dir, suffix=".jpg"
                ) as tmp_file:
                    tmp_file.write(response.content)
                    tmp_file.flush()
                    size = process_image_file(tmp_file.name)
                    return ProcessedImage(
                        path=tmp_file.name,
                        url=request.url,
                        content_type=response.headers["Content-Type"],
                        size=size,
                    )
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(2 * (attempt + 1))
                continue
            logger.error(f"Error processing image {request.url}: {str(e)}")
            return None

    return None


def convert_to_dict(obj: Any, collection_name: str) -> Dict[str, Any]:
    """Convert Pydantic model or dictionary to MongoDB-compatible dictionary."""
    if isinstance(obj, Property):
        # For Property objects, exclude both id and _id fields
        result = obj.model_dump(by_alias=True)
        result.pop("id", None)
        result.pop("_id", None)
        return result
    if hasattr(obj, "model_dump"):
        return obj.model_dump(by_alias=True)
    if isinstance(obj, dict):
        # For dictionaries, also remove id fields
        result = obj.copy()
        result.pop("id", None)
        result.pop("_id", None)
        return result

    logger.error(f"Unexpected object type in {collection_name}: {type(obj)}")
    return {}


def ensure_object_id(value: Any) -> Optional[ObjectId]:
    """Ensure a value is an ObjectId."""
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
    """Process property data and store in MongoDB."""
    if PROPERTIES not in item:
        logger.warning("No properties found in item")
        return None

    property_dict = convert_to_dict(item[PROPERTIES], "properties")

    # Log the incoming property data using structured logging for GCP
    logger.info(
        "Processing property",
        extra={
            "json_fields": {
                "property_name": property_dict.get("name"),
                "url": property_dict.get("url"),
                "redirected_url": property_dict.get("redirected_url"),
                "is_active": property_dict.get("is_active", True),
            }
        },
    )

    # Remove any id fields (should already be removed by convert_to_dict)
    property_dict.pop("id", None)
    property_dict.pop("_id", None)

    query = {"url": property_dict["url"]}
    existing = db[PROPERTIES].find_one(query)

    # Check if the URL is redirected to a library page using the redirected_url
    is_redirected_to_library = "/library/" in property_dict.get("redirected_url", "")
    current_time = get_current_time()

    if existing is not None:
        # Only update is_active and updated_at
        update_operation = {
            "$set": {
                "is_active": (
                    False
                    if is_redirected_to_library
                    else property_dict.get("is_active", True)
                ),
                "updated_at": current_time,
            },
            # Preserve existing values for these fields if they exist
            "$setOnInsert": {
                "image_urls": existing.get("image_urls", []),
                "created_at": existing.get("created_at", current_time),
                "large_property_description": existing.get(
                    "large_property_description", ""
                ),
                "small_property_description": existing.get(
                    "small_property_description", ""
                ),
                "name": existing.get("name", ""),
            },
        }

        db[PROPERTIES].update_one(query, update_operation)
        return existing["_id"]

    # For new properties, create a record with all fields
    property_dict["created_at"] = current_time
    property_dict["updated_at"] = current_time
    property_dict["is_active"] = (
        False if is_redirected_to_library else property_dict.get("is_active", True)
    )
    result = db[PROPERTIES].insert_one(property_dict)
    return result.inserted_id


def process_user_property(
    db: pymongo.MongoClient, item: Dict[str, Any], property_id: ObjectId
) -> Optional[ObjectId]:
    """Process user property data and store in MongoDB."""
    if USER_PROPERTIES not in item:
        return None

    user_property_dict = convert_to_dict(item[USER_PROPERTIES], "user_properties")

    # Ensure property_id is ObjectId
    user_property_dict["property_id"] = ensure_object_id(property_id)

    # Get line_user_id from user_properties
    if "line_user_id" not in user_property_dict:
        raise ValueError("line_user_id not found in user_properties")

    # Remove _id if it exists and is None
    if "_id" in user_property_dict and user_property_dict["_id"] is None:
        user_property_dict.pop("_id")

    query = {
        "line_user_id": user_property_dict["line_user_id"],
        "property_id": property_id,
    }

    existing = db[USER_PROPERTIES].find_one(query)
    current_time = get_current_time()

    if existing:
        # Only update tracking fields, preserve all other fields
        update_operation = {
            "$set": {
                "last_succeeded_at": current_time,
                "last_aggregated_at": current_time,
                "next_aggregated_at": current_time + timedelta(days=3),
            },
            # Preserve existing values
            "$setOnInsert": {
                k: existing.get(k)
                for k in existing
                if k
                not in [
                    "_id",
                    "last_succeeded_at",
                    "last_aggregated_at",
                    "next_aggregated_at",
                ]
            },
        }

        db[USER_PROPERTIES].update_one(query, update_operation)
        return existing["_id"]

    # For new records, include all fields
    user_property_dict.update(
        {
            "first_succeeded_at": current_time,
            "last_succeeded_at": current_time,
            "last_aggregated_at": current_time,
            "next_aggregated_at": current_time + timedelta(days=3),
            "created_at": current_time,
            "updated_at": current_time,
        }
    )
    result = db[USER_PROPERTIES].insert_one(user_property_dict)
    return result.inserted_id


def process_property_overview(
    db: pymongo.MongoClient, item: Dict[str, Any], property_id: ObjectId
) -> Optional[ObjectId]:
    """Process property overview data and store in MongoDB."""
    if PROPERTY_OVERVIEWS not in item:
        return None

    # Handle both model objects and dictionaries
    property_overview = item[PROPERTY_OVERVIEWS]
    if hasattr(property_overview, "property_id"):
        property_overview.property_id = property_id
        overview_dict = convert_to_dict(property_overview, "property_overviews")
    else:
        # If it's a dictionary, set property_id directly in the dict
        overview_dict = convert_to_dict(property_overview, "property_overviews")
        overview_dict["property_id"] = property_id

    # Ensure property_id is ObjectId
    overview_dict["property_id"] = ensure_object_id(property_id)

    if "_id" in overview_dict and overview_dict["_id"] is None:
        overview_dict.pop("_id")

    query = {"property_id": property_id}
    existing = db[PROPERTY_OVERVIEWS].find_one(query)
    current_time = get_current_time()

    if existing:
        # Only update price and updated_at, preserve other fields
        update_operation = {
            "$set": {
                "updated_at": current_time,
            }
        }

        # Create a list of fields to preserve, excluding price if it's in the new data
        fields_to_preserve = [k for k in existing if k not in ["_id", "updated_at"]]
        if "price" in overview_dict:
            fields_to_preserve.remove("price")
            update_operation["$set"]["price"] = overview_dict["price"]

        # Add $setOnInsert for preserving other fields
        update_operation["$setOnInsert"] = {
            k: existing.get(k) for k in fields_to_preserve
        }

        db[PROPERTY_OVERVIEWS].update_one(query, update_operation)
        return existing["_id"]

    # For new properties, create initial overview record
    overview_dict["created_at"] = current_time
    overview_dict["updated_at"] = current_time
    result = db[PROPERTY_OVERVIEWS].insert_one(overview_dict)
    return result.inserted_id


def process_common_overview(
    db: pymongo.MongoClient, item: Dict[str, Any], property_id: ObjectId
) -> Optional[ObjectId]:
    """Process common overview data and store in MongoDB."""
    if COMMON_OVERVIEWS not in item:
        return None

    overview_dict = convert_to_dict(item[COMMON_OVERVIEWS], "common_overviews")
    overview_dict["property_id"] = ensure_object_id(property_id)

    if "_id" in overview_dict and overview_dict["_id"] is None:
        overview_dict.pop("_id")

    query = {"property_id": property_id}
    existing = db[COMMON_OVERVIEWS].find_one(query)
    current_time = get_current_time()

    if existing:
        # Only update updated_at, preserve all other fields
        update_operation = {
            "$set": {
                "updated_at": current_time,
            },
            # Preserve existing values
            "$setOnInsert": {
                k: existing.get(k) for k in existing if k not in ["_id", "updated_at"]
            },
        }
        db[COMMON_OVERVIEWS].update_one(query, update_operation)
        return existing["_id"]

    # For new properties, create initial overview record
    overview_dict["created_at"] = current_time
    overview_dict["updated_at"] = current_time
    result = db[COMMON_OVERVIEWS].insert_one(overview_dict)
    return result.inserted_id


def process_image(image_file: str) -> io.BytesIO:
    """Process and optimize an image for upload."""
    with Image.open(image_file) as img:
        if img.mode == "RGBA":
            img = img.convert("RGB")

        quality = int(os.getenv("GCS_IMAGE_QUALITY", "50"))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        buffer.seek(0)
        return buffer


def get_gcs_url(bucket_name: str, blob_name: str) -> str:
    """Generate a publicly accessible URL for a GCS blob."""
    return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"


def upload_to_gcs(
    bucket: storage.bucket.Bucket, local_file: str, destination_blob_name: str
) -> bool:
    """Upload a file to Google Cloud Storage."""
    blob = bucket.blob(destination_blob_name)

    try:
        buffer = process_image(local_file)
        blob.upload_from_file(buffer, content_type="image/jpeg", rewind=True)
        blob.reload()
        return True
    except Exception as e:
        logger.error(f"Failed to upload image {destination_blob_name}: {e}")
        return False


def check_blob_exists(bucket: storage.bucket.Bucket, blob_name: str) -> bool:
    """Check if a blob exists in Google Cloud Storage."""
    try:
        blob = bucket.blob(blob_name)
        return blob.exists()
    except Exception as e:
        logger.error(f"Error checking if blob {blob_name} exists: {e}")
        return False


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
        return cls(
            mongo_uri=crawler.settings.get("MONGO_URI"),
            mongo_db=crawler.settings.get("MONGO_DATABASE"),
            images_store=crawler.settings.get("IMAGES_STORE"),
            gcp_bucket_name=crawler.settings.get("GCP_BUCKET_NAME"),
            gcp_folder_name=crawler.settings.get("GCP_FOLDER_NAME"),
        )

    def open_spider(self, spider):
        """Initialize MongoDB connection when spider opens."""
        self.logger.info(
            "Opening MongoDB connection",
            extra={
                "json_fields": {
                    "mongo_uri": (
                        self.mongo_uri.split("@")[-1]
                        if "@" in self.mongo_uri
                        else "masked"
                    ),
                    "mongo_db": self.mongo_db,
                }
            },
        )
        self.client = pymongo.MongoClient(self.mongo_uri, server_api=ServerApi("1"))
        self.db = self.client[self.mongo_db]

    def close_spider(self, spider):
        """Close MongoDB connection when spider closes."""
        if self.client:
            self.client.close()
        self.logger.info(
            "Completed MongoPipeline",
            extra={"json_fields": {"spider_name": spider.name}},
        )

    def process_item(self, item: ItemType, spider) -> ItemType:
        """Process items and store them in MongoDB."""
        try:
            property_id = process_property(self.db, item)
            if not property_id:
                return item

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
            self.logger.error(
                f"Error processing item: {e}",
                extra={
                    "json_fields": {
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "item_collections": [
                            k
                            for k in item.keys()
                            if k
                            in [
                                PROPERTIES,
                                USER_PROPERTIES,
                                PROPERTY_OVERVIEWS,
                                COMMON_OVERVIEWS,
                            ]
                        ],
                    }
                },
            )
            raise DropItem(f"Failed to process item: {e}")


class SuumoImagesPipeline(ImagesPipeline):
    """Pipeline for downloading and processing SUUMO property images."""

    def __init__(self, store_uri: str, download_func=None, settings=None, crawler=None):
        super().__init__(store_uri, download_func=download_func, crawler=crawler)
        self.logger = logging.getLogger(__name__)
        self.bucket_name = (
            settings.get("GCS_BUCKET_NAME", "mansion_watch")
            if settings
            else "mansion_watch"
        )
        self.storage_client = storage.Client()
        self.bucket = self.storage_client.bucket(self.bucket_name)
        self.logger.info(
            f"Successfully initialized Google Cloud Storage client with bucket: {self.bucket_name}"
        )

        self.tmp_dir = store_uri
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.image_url_to_gcs_url = {}

    @classmethod
    def from_crawler(cls, crawler):
        store_uri = crawler.settings.get("IMAGES_STORE", "tmp")
        return cls(store_uri, settings=crawler.settings, crawler=crawler)

    def open_spider(self, spider):
        """Initialize resources when spider opens."""
        super().open_spider(spider)
        self._initialize_storage(spider)

    def _initialize_storage(self, spider):
        """Initialize storage connections and settings."""
        # MongoDB setup
        mongo_uri = spider.settings.get("MONGO_URI")
        mongo_db = spider.settings.get("MONGO_DATABASE")
        self.client = pymongo.MongoClient(mongo_uri)
        self.db = self.client[mongo_db]
        self.images_store = spider.settings.get("IMAGES_STORE")

        # GCS setup
        self.gcp_bucket_name = spider.settings.get("GCP_BUCKET_NAME")
        self.folder_name = spider.settings.get("GCP_FOLDER_NAME")

        if not all([self.gcp_bucket_name, self.folder_name]):
            self.logger.info("GCS not configured - images will be stored locally only")
            return

        try:
            self._setup_gcs()
        except Exception as e:
            self._handle_gcs_setup_error(e)

    def _setup_gcs(self):
        """Set up Google Cloud Storage client and bucket."""
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not credentials_path:
            raise ValueError("Missing GCP credentials path")
        if not os.path.exists(credentials_path):
            raise FileNotFoundError(
                f"GCP credentials file not found: {credentials_path}"
            )

        self.storage_client = storage.Client()
        self.bucket = self.storage_client.bucket(self.gcp_bucket_name)

        if not self.bucket.exists():
            raise ValueError(f"GCS bucket '{self.gcp_bucket_name}' does not exist")

        self.logger.info(
            f"Successfully initialized Google Cloud Storage client with bucket: {self.gcp_bucket_name}"
        )

    def _handle_gcs_setup_error(self, error: Exception):
        """Handle errors during GCS setup."""
        self.logger.error(f"Failed to initialize Google Cloud Storage: {str(error)}")
        self.logger.error("Make sure you have:")
        self.logger.error("1. Set GOOGLE_APPLICATION_CREDENTIALS environment variable")
        self.logger.error(
            "2. Placed the service-account.json file in the correct location"
        )
        self.logger.error("3. Granted necessary permissions to the service account")
        raise error

    def close_spider(self, spider):
        """Clean up resources when spider closes."""
        if self.client:
            self.client.close()
        if self.storage_client:
            self.storage_client.close()
        self._cleanup_temp_directory()
        self.logger.info("Completed SuumoImagesPipeline")

    def get_media_requests(self, item: Dict[str, Any], info) -> List[Request]:
        """Get requests for downloading images."""
        image_urls = item.get("image_urls", [])
        if not image_urls:
            return []

        return [
            Request(
                url=url,
                headers=create_image_request(url).headers,
                meta={"download_timeout": 30},
                dont_filter=True,
            )
            for url in image_urls
            if url
        ]

    def _process_single_request(self, request: Request) -> Optional[str]:
        """Process a single image request."""
        image_request = create_image_request(request.url)
        processed = download_image(image_request, self.tmp_dir)
        return processed.path if processed else None

    def _get_blob_name(self, url: str) -> str:
        """Generate a unique and safe blob name for GCS storage.

        Args:
            url: Original image URL from SUUMO
        Returns:
            A sanitized blob name suitable for GCS
        """
        try:
            # Decode the URL first
            decoded_url = urllib.parse.unquote(url)

            # For SUUMO URLs, extract the actual image path from the src parameter
            if "resizeImage" in decoded_url:
                parsed_qs = urllib.parse.parse_qs(
                    urllib.parse.urlparse(decoded_url).query
                )
                if "src" in parsed_qs:
                    # Get the actual image path from src parameter
                    image_path = urllib.parse.unquote(parsed_qs["src"][0])
                    # Extract meaningful parts from the path
                    parts = image_path.split("/")
                    if len(parts) >= 2:
                        # Use the last two parts of the path to create a unique filename
                        filename = f"{parts[-2]}_{parts[-1]}"
                    else:
                        filename = parts[-1]
                else:
                    # Fallback to hash if src parameter is not found
                    hash_object = hashlib.md5(decoded_url.encode())
                    filename = f"image_{hash_object.hexdigest()[:10]}.jpg"
            else:
                # For non-resizeImage URLs, use the last part of the path
                filename = os.path.basename(decoded_url)
                if not filename or filename.startswith("?"):
                    hash_object = hashlib.md5(decoded_url.encode())
                    filename = f"image_{hash_object.hexdigest()[:10]}.jpg"

            # Ensure the filename has a proper extension
            if not filename.lower().endswith((".jpg", ".jpeg", ".png", ".gif")):
                filename += ".jpg"

            # Remove any query parameters from the filename
            filename = filename.split("?")[0]

            # Sanitize the filename to remove any potentially problematic characters
            filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)

            return f"{self.folder_name}/{filename}"
        except Exception as e:
            self.logger.error(f"Error generating blob name for URL {url}: {str(e)}")
            # Fallback to hash in case of any error
            hash_object = hashlib.md5(url.encode())
            return f"{self.folder_name}/image_{hash_object.hexdigest()[:10]}.jpg"

    def _upload_to_gcs(self, image_path: str, original_url: str) -> Optional[str]:
        """Upload the image to Google Cloud Storage."""
        try:
            blob_name = self._get_blob_name(original_url)

            # Double check if image exists before uploading
            if check_blob_exists(self.bucket, blob_name):
                return f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"

            blob = self.bucket.blob(blob_name)

            # Upload the file without ACL parameter
            blob.upload_from_filename(
                image_path, content_type="image/jpeg"  # Set the content type explicitly
            )

            return f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"
        except Exception as e:
            self.logger.error(f"Error uploading to GCS: {str(e)}, URL: {original_url}")
            return None

    def _upload_image_to_gcs(self, image_path: str, original_url: str) -> Optional[str]:
        """Upload an image to Google Cloud Storage."""
        return self._upload_to_gcs(image_path, original_url)

    def _get_property_name(self, item: Dict[str, Any]) -> str:
        """Extract property name from item."""
        properties = item.get("properties", {})
        if isinstance(properties, Property):
            return properties.name
        elif isinstance(properties, dict):
            return properties.get("name", "Unknown")
        return "Unknown"

    def _process_existing_image(
        self, request: Request, blob_name: str
    ) -> Optional[str]:
        """Handle image that already exists in storage."""
        gcs_url = f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"
        self.logger.debug(f"Image already exists in GCS: {blob_name}")
        # Cache the URL for future use
        self.image_url_to_gcs_url[request.url] = gcs_url
        return gcs_url

    def _process_new_image(self, request: Request, blob_name: str) -> Optional[str]:
        """Download and upload a new image."""
        self.logger.debug(f"Downloading image from: {request.url}")
        image_path = self._process_single_request(request)
        if not image_path:
            self.logger.error(f"Failed to process image: {request.url}")
            return None

        self.logger.debug(f"Uploading image to GCS: {blob_name}")
        gcs_url = self._upload_to_gcs(image_path, request.url)
        if not gcs_url:
            self.logger.error(f"Failed to upload image to GCS: {request.url}")
            return None

        # Cache the URL for future use
        self.image_url_to_gcs_url[request.url] = gcs_url
        self.logger.debug(f"Successfully uploaded image to: {gcs_url}")
        return gcs_url

    def _update_item_image_urls(
        self, item: Dict[str, Any], processed_urls: List[str]
    ) -> None:
        """Update item with processed image URLs."""
        if not processed_urls:
            return

        item["image_urls"] = processed_urls
        properties = item.get("properties")
        if isinstance(properties, Property):
            properties.image_urls = processed_urls
        elif properties is not None:
            item["properties"]["image_urls"] = processed_urls

    def process_item(self, item: Dict[str, Any], spider) -> Dict[str, Any]:
        """Process each item and handle image downloads."""
        image_urls = item.get("image_urls", [])
        if not image_urls:
            self.logger.warning(
                "No image URLs found in item",
                extra={"json_fields": {"item_keys": list(item.keys())}},
            )
            return item

        requests = self.get_media_requests(item, spider)
        if not requests:
            self.logger.warning(
                "No media requests generated for item",
                extra={"json_fields": {"image_urls": image_urls}},
            )
            return item

        processed_urls = []
        existing_images = 0
        new_uploads = 0
        failed_uploads = 0
        property_name = self._get_property_name(item)

        self.logger.info(
            f"Starting to process {len(requests)} images for property: {property_name}",
            extra={
                "json_fields": {
                    "property_name": property_name,
                    "image_count": len(requests),
                }
            },
        )

        for i, request in enumerate(requests, 1):
            blob_name = self._get_blob_name(request.url)
            self.logger.debug(f"Processing image {i}/{len(requests)}: {request.url}")

            # Check if image already exists in GCS
            if check_blob_exists(self.bucket, blob_name):
                gcs_url = self._process_existing_image(request, blob_name)
                processed_urls.append(gcs_url)
                existing_images += 1
                continue

            # Process new image
            gcs_url = self._process_new_image(request, blob_name)
            if gcs_url:
                processed_urls.append(gcs_url)
                new_uploads += 1
            else:
                failed_uploads += 1

        # Log summary of processed images
        total_images = len(requests)
        self.logger.info(
            f"Image processing summary for {property_name}: "
            f"Total: {total_images}, Existing: {existing_images}, "
            f"New uploads: {new_uploads}, Failed: {failed_uploads}",
            extra={
                "json_fields": {
                    "property_name": property_name,
                    "total_images": total_images,
                    "existing_images": existing_images,
                    "new_uploads": new_uploads,
                    "failed_uploads": failed_uploads,
                }
            },
        )

        # Update item with processed URLs
        self._update_item_image_urls(item, processed_urls)

        return item

    def _cleanup_temp_directory(self, directory: Optional[str] = None) -> bool:
        """Clean up temporary directory."""
        try:
            target_dir = directory or self.images_store
            if not target_dir or not os.path.exists(target_dir):
                return False

            tmp_dir = os.path.dirname(target_dir)
            if os.path.exists(tmp_dir):
                import shutil

                shutil.rmtree(tmp_dir)
            return True
        except Exception as e:
            self.logger.error(f"Error cleaning up temporary directory: {e}")
            return False

    def _count_failed_downloads(self, results):
        """Count and log failed downloads.

        Args:
            results: List of download results
        Returns:
            Number of failed downloads
        """
        failed_downloads = len([r for r, i in results if not r])
        if failed_downloads > 0:
            self.logger.warning(f"Failed to download {failed_downloads} images")
        return failed_downloads

    def _get_successful_downloads(self, results):
        """Extract successful downloads from results.

        Args:
            results: List of download results
        Returns:
            List of successful download results
        """
        return [
            result[1] for result in results if result[0] and isinstance(result[1], dict)
        ]

    def _process_successful_downloads(self, successful_downloads):
        """Process successful downloads and get GCS URLs.

        Args:
            successful_downloads: List of successful download results
        Returns:
            List of GCS URLs
        """
        gcs_urls = []
        for download in successful_downloads:
            if "path" in download:
                url = self._upload_image_to_gcs(download["path"], download["url"])
                if url:
                    gcs_urls.append(url)
                    # Cache the mapping between original URL and GCS URL
                    if "url" in download:
                        self.image_url_to_gcs_url[download["url"]] = url
        return gcs_urls

    def _get_cached_gcs_urls(self, results):
        """Get cached GCS URLs for failed downloads.

        Args:
            results: List of download results
        Returns:
            List of cached GCS URLs
        """
        cached_urls = []
        for result in results:
            if not result[0] and isinstance(result[1], Exception):
                original_url = getattr(result[1], "url", None)
                if original_url and original_url in self.image_url_to_gcs_url:
                    cached_urls.append(self.image_url_to_gcs_url[original_url])
        return cached_urls

    def _update_item_urls(self, item, gcs_urls):
        """Update item with GCS URLs.

        Args:
            item: Item to update
            gcs_urls: List of GCS URLs
        """
        if not gcs_urls:
            return

        self.logger.info(f"Successfully processed {len(gcs_urls)} images")
        properties = item.get("properties")
        if isinstance(properties, Property):
            properties.image_urls = gcs_urls
        elif properties is not None:
            item["properties"]["image_urls"] = gcs_urls

    def item_completed(self, results, item, info):
        """Process completed downloads."""
        if not results:
            return item

        # Count failed downloads
        self._count_failed_downloads(results)

        # Process successful downloads
        successful_downloads = self._get_successful_downloads(results)
        gcs_urls = self._process_successful_downloads(successful_downloads)

        # Get cached GCS URLs for failed downloads
        cached_urls = self._get_cached_gcs_urls(results)
        gcs_urls.extend(cached_urls)

        # Update item with all GCS URLs
        self._update_item_urls(item, gcs_urls)

        return item
