"""
Scrapy pipelines for processing and storing scraped data.

This module contains pipelines for:
1. Storing data in MongoDB
2. Processing and uploading images to Google Cloud Storage
"""

import io
import logging
import os
import tempfile
import time
from dataclasses import dataclass
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
        return None

    property_dict = convert_to_dict(item[PROPERTIES], "properties")

    # Remove any id fields (should already be removed by convert_to_dict)
    property_dict.pop("id", None)
    property_dict.pop("_id", None)

    query = {"url": property_dict["url"]}
    existing = db[PROPERTIES].find_one(query)

    if existing is not None:
        property_dict = {
            k: v for k, v in property_dict.items() if k not in ["created_at"]
        }
        db[PROPERTIES].update_one(query, {"$set": property_dict})
        return existing["_id"]

    result = db[PROPERTIES].insert_one(property_dict)
    return result.inserted_id


def process_user_property(
    db: pymongo.MongoClient, item: Dict[str, Any], property_id: ObjectId
) -> Optional[ObjectId]:
    """Process user property data and store in MongoDB."""
    if USER_PROPERTIES not in item:
        return None

    user_property_dict = convert_to_dict(item[USER_PROPERTIES], "user_properties")
    user_property_dict["property_id"] = property_id
    user_property_obj = UserProperty(**user_property_dict)
    user_property_dict = convert_to_dict(user_property_obj, "user_properties")

    if "_id" in user_property_dict and user_property_dict["_id"] is None:
        user_property_dict.pop("_id")

    if "property_id" in user_property_dict:
        user_property_dict["property_id"] = ensure_object_id(
            user_property_dict["property_id"]
        )

    query = {
        "line_user_id": user_property_dict["line_user_id"],
        "property_id": property_id,
    }

    existing = db[USER_PROPERTIES].find_one(query)
    current_time = get_current_time()

    if existing:
        update_data = {
            **user_property_dict,
            "last_succeeded_at": current_time,
        }
        for field in ["_id", "first_succeeded_at", "created_at"]:
            update_data.pop(field, None)

        db[USER_PROPERTIES].update_one(query, {"$set": update_data})
        return existing["_id"]

    user_property_dict.update(
        {
            "last_succeeded_at": current_time,
            "first_succeeded_at": current_time,
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

    item[PROPERTY_OVERVIEWS].property_id = property_id
    overview_dict = convert_to_dict(item[PROPERTY_OVERVIEWS], "property_overviews")

    if "_id" in overview_dict and overview_dict["_id"] is None:
        overview_dict.pop("_id")

    if "property_id" in overview_dict:
        overview_dict["property_id"] = ensure_object_id(overview_dict["property_id"])

    query = {"property_id": property_id}
    existing = db[PROPERTY_OVERVIEWS].find_one(query)

    if existing:
        for field in ["_id", "created_at"]:
            overview_dict.pop(field, None)
        db[PROPERTY_OVERVIEWS].update_one(query, {"$set": overview_dict})
        return existing["_id"]

    result = db[PROPERTY_OVERVIEWS].insert_one(overview_dict)
    return result.inserted_id


def process_common_overview(
    db: pymongo.MongoClient, item: Dict[str, Any], property_id: ObjectId
) -> Optional[ObjectId]:
    """Process common overview data and store in MongoDB."""
    if COMMON_OVERVIEWS not in item:
        return None

    item[COMMON_OVERVIEWS].property_id = property_id
    overview_dict = convert_to_dict(item[COMMON_OVERVIEWS], "common_overviews")

    if "_id" in overview_dict and overview_dict["_id"] is None:
        overview_dict.pop("_id")

    if "property_id" in overview_dict:
        overview_dict["property_id"] = ensure_object_id(overview_dict["property_id"])

    query = {"property_id": property_id}
    existing = db[COMMON_OVERVIEWS].find_one(query)

    if existing:
        for field in ["_id", "created_at"]:
            overview_dict.pop(field, None)
        db[COMMON_OVERVIEWS].update_one(query, {"$set": overview_dict})
        return existing["_id"]

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
        self.logger.info("Opening MongoDB connection")
        self.client = pymongo.MongoClient(self.mongo_uri, server_api=ServerApi("1"))
        self.db = self.client[self.mongo_db]

    def close_spider(self, spider):
        """Close MongoDB connection when spider closes."""
        if self.client:
            self.client.close()
        self.logger.info("Completed MongoPipeline")

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
            self.logger.error(f"Error processing item: {e}")
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

    def process_item(self, item: Dict[str, Any], spider) -> Dict[str, Any]:
        """Process each item and handle image downloads."""
        image_urls = item.get("image_urls", [])
        if not image_urls:
            self.logger.warning("No image URLs found in item")
            return item

        requests = self.get_media_requests(item, spider)
        if not requests:
            self.logger.warning("No media requests generated for item")
            return item

        processed_urls = []
        existing_images = 0
        new_uploads = 0

        for request in requests:
            filename = os.path.basename(request.url)
            blob_name = f"{self.folder_name}/{filename}"

            # Check if image already exists in GCS
            if check_blob_exists(self.bucket, blob_name):
                gcs_url = (
                    f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"
                )
                processed_urls.append(gcs_url)
                # Cache the URL for future use
                self.image_url_to_gcs_url[request.url] = gcs_url
                existing_images += 1
                continue

            image_path = self._process_single_request(request)
            if not image_path:
                self.logger.error(f"Failed to process image: {request.url}")
                continue

            gcs_url = self._upload_to_gcs(image_path, request.url)
            if not gcs_url:
                self.logger.error(f"Failed to upload image to GCS: {request.url}")
                continue

            processed_urls.append(gcs_url)
            # Cache the URL for future use
            self.image_url_to_gcs_url[request.url] = gcs_url
            new_uploads += 1

        # Log summary of processed images
        total_images = len(requests)
        self.logger.info(
            f"Image processing summary - Total: {total_images}, "
            f"Existing: {existing_images}, New uploads: {new_uploads}, "
            f"Failed: {total_images - (existing_images + new_uploads)}"
        )

        if processed_urls:
            item["image_urls"] = processed_urls
            properties = item.get("properties")
            if isinstance(properties, Property):
                properties.image_urls = processed_urls
            elif properties is not None:
                item["properties"]["image_urls"] = processed_urls

        return item

    def _upload_to_gcs(self, image_path: str, original_url: str) -> Optional[str]:
        """Upload the image to Google Cloud Storage."""
        try:
            filename = os.path.basename(original_url)
            blob_name = f"{self.folder_name}/{filename}"

            # Double check if image exists before uploading
            if check_blob_exists(self.bucket, blob_name):
                return f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"

            blob = self.bucket.blob(blob_name)
            blob.upload_from_filename(image_path)
            return f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"
        except Exception as e:
            self.logger.error(f"Error uploading to GCS: {str(e)}")
            return None

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
                self.logger.info(
                    f"Cleaned up tmp directory and all contents: {tmp_dir}"
                )
            return True
        except Exception as e:
            self.logger.error(f"Error cleaning up temporary directory: {e}")
            return False

    def item_completed(self, results, item, info):
        """Process completed downloads."""
        if not results:
            return item

        # Count failed downloads
        failed_downloads = len([r for r, i in results if not r])
        if failed_downloads > 0:
            self.logger.warning(f"Failed to download {failed_downloads} images")

        # Process successful downloads
        successful_downloads = [
            result[1] for result in results if result[0] and isinstance(result[1], dict)
        ]

        # Process successful downloads and get GCS URLs
        gcs_urls = self._process_successful_downloads(successful_downloads)

        # Update the item with GCS URLs
        properties = item.get("properties")
        if isinstance(properties, Property):
            properties.image_urls = gcs_urls
        else:
            item["properties"]["image_urls"] = gcs_urls

        return item

    def _process_successful_downloads(self, image_paths: List[str]) -> List[str]:
        """Process successful downloads and upload to GCS."""
        gcs_image_urls = []
        for path in image_paths:
            url = self._upload_image_to_gcs(path)
            if url:
                gcs_image_urls.append(url)

        if gcs_image_urls:
            self.logger.info(
                f"Successfully uploaded {len(gcs_image_urls)} images to GCS"
            )

        return gcs_image_urls

    def _upload_image_to_gcs(self, image_path: str) -> Optional[str]:
        """Upload an image to Google Cloud Storage."""
        try:
            filename = os.path.basename(image_path)
            blob_name = f"{self.folder_name}/{filename}"

            # Check if image already exists in GCS
            if check_blob_exists(self.bucket, blob_name):
                return f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"

            blob = self.bucket.blob(blob_name)
            blob.upload_from_filename(image_path)
            return f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"
        except Exception as e:
            self.logger.error(f"Error uploading image to GCS: {str(e)}")
            return None
