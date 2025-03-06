"""
Scrapy pipelines for processing and storing scraped data.

This module contains pipelines for:
1. Storing data in MongoDB
2. Processing and uploading images to Google Cloud Storage
"""

import io
import logging
import os
from typing import Any, Dict, Optional, Tuple, TypeVar, Union

import pymongo
import scrapy
from bson import ObjectId
from google.cloud import storage
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
        quality = int(os.getenv("GCS_IMAGE_QUALITY", "50"))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        buffer.seek(0)  # Reset buffer position to beginning

        return buffer


def get_gcs_url(bucket_name: str, blob_name: str) -> str:
    """
    Generate a publicly accessible URL for a GCS blob.

    Args:
        bucket_name: Name of the GCS bucket
        blob_name: Name of the blob

    Returns:
        Public URL string
    """
    return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"


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

        # Upload the processed buffer with public-read ACL
        blob.upload_from_file(
            buffer,
            content_type="image/jpeg",
            rewind=True,
            predefined_acl="publicRead",  # Make the uploaded object publicly readable
        )

        # Verify uploaded file
        blob.reload()
        return True

    except Exception as e:
        logger.error(f"Failed to upload image {destination_blob_name}: {e}")
        return False


def check_blob_exists(bucket: storage.bucket.Bucket, blob_name: str) -> bool:
    """
    Check if a blob exists in Google Cloud Storage.

    Args:
        bucket: GCS bucket
        blob_name: Name of the blob to check

    Returns:
        True if blob exists, False otherwise
    """
    try:
        blob = bucket.blob(blob_name)
        return blob.exists()
    except Exception as e:
        logger.error(f"Error checking if blob {blob_name} exists: {e}")
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

        # Cache for storing image URL to GCS URL mapping
        self.image_url_to_gcs_url = {}

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

        # Clean up the tmp directory in one operation
        self._cleanup_temp_directory()

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
        import re
        import urllib.parse

        # Extract the src parameter from the URL if it exists
        url = request.url
        if "resizeImage?src=" in url:
            # Parse the URL to get the query parameters
            parsed_url = urllib.parse.urlparse(url)
            query_params = urllib.parse.parse_qs(parsed_url.query)

            # Get the src parameter and decode it
            if "src" in query_params:
                src = urllib.parse.unquote(query_params["src"][0])

                # Extract the filename using regex
                match = re.search(r"(\d+_\d+\.jpg)$", src)
                if match:
                    return match.group(1)

        # Fallback to the last part of the URL if we can't extract a clean filename
        return url.split("/")[-1]

    def get_media_requests(self, item, info):
        """
        Get media requests for image downloads.

        Args:
            item: Scraped item
            info: Pipeline info

        Returns:
            Iterator of Scrapy requests
        """
        # Get image URLs from properties
        image_urls = self._get_image_urls_from_item(item)
        if not image_urls:
            return []

        # Get common headers for image requests
        headers = self._get_request_headers()

        # If GCS is not configured, download all images
        if not self._is_gcs_configured():
            return self._create_requests_for_all_images(image_urls, headers)

        # Process each image URL with GCS check
        return self._process_image_urls_with_gcs_check(image_urls, headers)

    def _get_image_urls_from_item(self, item):
        """
        Extract image URLs from the item.

        Args:
            item: Scraped item

        Returns:
            List of image URLs or empty list if none found
        """
        properties = item.get(PROPERTIES)
        if not properties:
            self.logger.warning("No properties found in item")
            return []

        # Check if the property is inactive (sold-out)
        is_active = properties.is_active if hasattr(properties, "is_active") else True

        image_urls = properties.image_urls if hasattr(properties, "image_urls") else []
        if not image_urls:
            if not is_active:
                # For sold-out properties, log a different message
                self.logger.info(
                    "Property is sold out (redirected to library page), no images expected"
                )
            else:
                # For active properties with no images, log a warning
                self.logger.warning("No image URLs found in item")
            return []

        return image_urls

    def _get_request_headers(self):
        """
        Get common headers for image requests.

        Returns:
            Dictionary of request headers
        """
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Referer": "https://suumo.jp/",
        }

    def _is_gcs_configured(self):
        """
        Check if GCS is properly configured.

        Returns:
            True if GCS is configured, False otherwise
        """
        return bool(self.bucket and self.folder_name)

    def _create_requests_for_all_images(self, image_urls, headers):
        """
        Create requests for all image URLs without GCS check.

        Args:
            image_urls: List of image URLs
            headers: Request headers

        Returns:
            Iterator of Scrapy requests
        """
        for image_url in image_urls:
            yield from self._create_request_if_valid(image_url, headers)

    def _process_image_urls_with_gcs_check(self, image_urls, headers):
        """
        Process image URLs with GCS existence check.

        Args:
            image_urls: List of image URLs
            headers: Request headers

        Returns:
            Iterator of Scrapy requests
        """
        existing_images = []
        for image_url in image_urls:
            for request in self._process_single_image_url(
                image_url, headers, existing_images
            ):
                yield request

        # Log existing images as a chunk if any were found
        if existing_images:
            self.logger.info(f"{len(existing_images)} images already exist in GCS")

    def _process_single_image_url(self, image_url, headers, existing_images=None):
        """
        Process a single image URL with GCS existence check.

        Args:
            image_url: Image URL
            headers: Request headers
            existing_images: Optional list to collect existing image URLs

        Returns:
            Iterator of Scrapy requests
        """
        try:
            # Skip invalid URLs
            if not self._is_valid_url(image_url):
                return

            # Determine the filename that would be used
            filename = self._get_filename_from_url(image_url)
            if not filename:
                self.logger.warning(
                    f"Could not determine filename for URL: {image_url}"
                )
                yield from self._create_request_if_valid(image_url, headers)
                return

            # Check if the image already exists in GCS
            destination_blob_name = f"{self.folder_name}/{filename}"
            if check_blob_exists(self.bucket, destination_blob_name):
                # Image already exists in GCS, store the GCS URL in cache
                gcs_url = get_gcs_url(self.gcp_bucket_name, destination_blob_name)
                self.image_url_to_gcs_url[image_url] = gcs_url

                # Add to existing_images list instead of logging individually
                if existing_images is not None:
                    existing_images.append(gcs_url)
                return

            # Image doesn't exist in GCS, create a request to download it
            yield from self._create_request_if_valid(image_url, headers)
        except Exception as e:
            self.logger.error(f"Error processing URL {image_url}: {e}")

    def _is_valid_url(self, url):
        """
        Check if a URL is valid.

        Args:
            url: URL to check

        Returns:
            True if URL is valid, False otherwise
        """
        if not url or not isinstance(url, str):
            self.logger.warning(f"Invalid image URL: {url}")
            return False

        url = url.strip()
        if not url:
            return False

        return True

    def _create_request_if_valid(self, image_url, headers):
        """
        Create a request for a valid image URL.

        Args:
            image_url: URL of the image
            headers: Request headers

        Returns:
            Iterator of Scrapy requests
        """
        try:
            if not self._is_valid_url(image_url):
                return

            yield scrapy.Request(
                url=image_url,
                headers=headers,
                meta={
                    "max_retry_times": 3,  # Allow up to 3 retries
                    "download_timeout": 60,  # Increase timeout to 60 seconds
                    "retry_times": 0,  # Initialize retry counter
                },
                dont_filter=True,  # Important: Bypass the OffsiteMiddleware filter
                errback=self._handle_download_error,  # Add error handling callback
            )
        except Exception as e:
            self.logger.error(f"Error creating request for URL {image_url}: {e}")

    def _handle_download_error(self, failure):
        """
        Handle download errors and implement retry logic.

        Args:
            failure: Twisted failure object containing error information

        Returns:
            New request if retries are available, None otherwise
        """
        request = failure.request
        retry_times = request.meta.get("retry_times", 0)
        max_retry_times = request.meta.get("max_retry_times", 3)

        if retry_times < max_retry_times:
            retry_times += 1
            new_request = request.copy()
            new_request.meta["retry_times"] = retry_times
            new_request.dont_filter = True
            self.logger.info(
                f"Retrying {request.url} (attempt {retry_times + 1} of {max_retry_times + 1})"
            )
            return new_request
        else:
            self.logger.warning(
                f"Failed to download {request.url} after {max_retry_times + 1} attempts"
            )
            return None

    def _get_filename_from_url(self, url):
        """
        Extract filename from URL using the same logic as file_path.

        Args:
            url: Image URL

        Returns:
            Extracted filename or None if extraction fails
        """
        try:
            import re
            import urllib.parse

            # Extract the src parameter from the URL if it exists
            if "resizeImage?src=" in url:
                # Parse the URL to get the query parameters
                parsed_url = urllib.parse.urlparse(url)
                query_params = urllib.parse.parse_qs(parsed_url.query)

                # Get the src parameter and decode it
                if "src" in query_params:
                    src = urllib.parse.unquote(query_params["src"][0])

                    # Extract the filename using regex
                    match = re.search(r"(\d+_\d+\.jpg)$", src)
                    if match:
                        return match.group(1)

            # Fallback to the last part of the URL
            return url.split("/")[-1]
        except Exception as e:
            self.logger.error(f"Error extracting filename from URL {url}: {e}")
            return None

    def _process_failed_downloads(self, failed_downloads):
        """Process and log failed downloads."""
        if failed_downloads:
            self.logger.warning(f"Failed to download {len(failed_downloads)} images")
            for failure in failed_downloads:
                if isinstance(failure, Exception):
                    self.logger.warning(f"Download failure: {str(failure)}")

    def _upload_image_to_gcs(self, image_path):
        """Upload a single image to GCS and return the GCS URL if successful."""
        try:
            # Construct local file path
            local_file = os.path.join(self.images_store, image_path)

            # Construct GCS destination path
            destination_blob_name = f"{self.folder_name}/{image_path}"

            # Upload to GCS
            success = upload_to_gcs(self.bucket, local_file, destination_blob_name)

            if success:
                # Construct GCS URL using the get_gcs_url function
                gcs_url = get_gcs_url(self.gcp_bucket_name, destination_blob_name)
                return gcs_url
            return None
        except Exception as e:
            self.logger.error(f"Error uploading image {image_path} to GCS: {e}")
            return None

    def _cleanup_temp_directory(self, directory=None):
        """
        Clean up temporary directory by removing all files and the directory itself.

        Args:
            directory: Directory to clean up. If None, uses self.images_store

        Returns:
            bool: True if cleanup was successful, False otherwise
        """
        try:
            target_dir = directory or self.images_store
            if not target_dir or not os.path.exists(target_dir):
                return False

            # Use shutil.rmtree for efficient recursive directory removal
            import shutil

            shutil.rmtree(target_dir)
            self.logger.info(f"Cleaned up temporary directory: {target_dir}")
            return True
        except Exception as e:
            self.logger.error(
                f"Error cleaning up temporary directory {target_dir}: {e}"
            )
            return False

    def _process_successful_downloads(self, image_paths, property_id):
        """Process successful downloads and upload to GCS."""
        # Upload images to GCS if configured
        if not (self.bucket and self.folder_name):
            return []

        # Upload each image to GCS and collect URLs
        gcs_image_urls = [
            url
            for url in (self._upload_image_to_gcs(path) for path in image_paths)
            if url
        ]

        self.logger.info(f"Uploaded {len(gcs_image_urls)} images to GCS")

        # No need to clean up individual files here - we'll clean up everything at once later
        return gcs_image_urls

    def _log_image_processing_results(
        self, original_image_count, existing_image_count, new_gcs_urls, failed_downloads
    ):
        """
        Log image processing results based on what actually happened.

        Args:
            original_image_count: Total number of original image URLs
            existing_image_count: Number of images that already existed in GCS
            new_gcs_urls: List of newly uploaded GCS URLs
            failed_downloads: List of failed downloads
        """
        if new_gcs_urls:
            if existing_image_count > 0:
                # Mix of existing and new images
                self.logger.info(
                    f"Updated item with {existing_image_count + len(new_gcs_urls)} GCS image URLs "
                    f"({existing_image_count} already existed, {len(new_gcs_urls)} newly uploaded)"
                )
            else:
                # Only new images
                self.logger.info(
                    f"Updated item with {len(new_gcs_urls)} newly uploaded GCS image URLs"
                )
        elif existing_image_count > 0 and original_image_count > existing_image_count:
            # Some images existed but others failed to download/upload
            self.logger.info(
                f"Partial update: {existing_image_count} of {original_image_count} "
                f"images already existed in GCS, {original_image_count - existing_image_count - len(failed_downloads)} "
                f"failed to process"
            )
        # No log if all images already existed (to avoid confusion)

    def item_completed(self, results, item, info):
        """
        Handle completed item processing with proper cleanup and error handling.

        Args:
            results: Results from image downloads
            item: Scraped item
            info: Pipeline info

        Returns:
            Processed item
        """
        try:
            # Get properties from item
            properties = item.get(PROPERTIES)
            if not properties:
                return item

            # Get original image URLs
            original_image_urls = (
                properties.image_urls if hasattr(properties, "image_urls") else []
            )
            if not original_image_urls:
                return item

            # Gather successful image paths
            image_paths = [res["path"] for ok, res in results if ok]

            # Process failed downloads
            failed_downloads = [res for ok, res in results if not ok]
            self._process_failed_downloads(failed_downloads)

            # Get property ID for organizing images
            property_id = properties._id if hasattr(properties, "_id") else None

            # Combine GCS URLs from cache and newly uploaded images
            gcs_image_urls = []

            # First add URLs from cache (images that already existed in GCS)
            existing_image_count = 0
            for url in original_image_urls:
                if url in self.image_url_to_gcs_url:
                    gcs_image_urls.append(self.image_url_to_gcs_url[url])
                    existing_image_count += 1

            # Then process and upload new images
            new_gcs_urls = []
            if image_paths:
                new_gcs_urls = self._process_successful_downloads(
                    image_paths, property_id
                )
                gcs_image_urls.extend(new_gcs_urls)

            # Update item with all GCS image URLs
            if hasattr(properties, "image_urls"):
                properties.image_urls = gcs_image_urls

                # Log results based on what actually happened
                self._log_image_processing_results(
                    len(original_image_urls),
                    existing_image_count,
                    new_gcs_urls,
                    failed_downloads,
                )

            return item
        except Exception as e:
            self.logger.error(f"Error processing images: {e}")
            # Continue processing even if image handling fails
            return item
