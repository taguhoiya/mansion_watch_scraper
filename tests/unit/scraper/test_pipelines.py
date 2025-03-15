import datetime
import io
import logging
import os
from unittest.mock import MagicMock, Mock, patch

import pytest
import scrapy
from bson import ObjectId
from google.cloud import storage
from PIL import Image
from scrapy.exceptions import DropItem
from scrapy.settings import Settings

from app.models.property import Property
from app.models.user_property import UserProperty
from mansion_watch_scraper.pipelines import (
    MongoPipeline,
    SuumoImagesPipeline,
    convert_to_dict,
    ensure_object_id,
    process_image,
    upload_to_gcs,
)


@pytest.fixture
def mock_image():
    """Create a mock image for testing."""
    img = Image.new("RGB", (100, 100), color="red")
    img_buffer = io.BytesIO()
    img.save(img_buffer, format="JPEG")
    img_buffer.seek(0)
    return img_buffer


@pytest.fixture
def mock_storage_client():
    """Create a mock GCS client."""
    with patch("google.cloud.storage.Client") as mock:
        yield mock


@pytest.fixture
def mock_bucket(mock_storage_client):
    """Create a mock GCS bucket."""
    mock_bucket = MagicMock(spec=storage.bucket.Bucket)
    mock_storage_client.bucket.return_value = mock_bucket
    return mock_bucket


class TestConvertToDict:
    """Test cases for convert_to_dict function."""

    def test_convert_property_to_dict(self):
        """Test converting a Property model to dict."""
        current_time = datetime.datetime(
            2024, 3, 15, 12, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=9))
        )
        property_data = {
            "name": "Test Property",
            "url": "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_95982188/",
            "is_active": True,
            "created_at": current_time,
            "updated_at": current_time,
        }
        property_obj = Property(**property_data)
        result = convert_to_dict(property_obj, "properties")

        assert isinstance(result, dict)
        assert "id" not in result  # Should exclude id field
        assert result["name"] == property_data["name"]
        assert result["url"] == property_data["url"]
        assert result["is_active"] == property_data["is_active"]
        assert result["created_at"] == current_time
        assert result["updated_at"] == current_time

    def test_convert_user_property_to_dict(self):
        """Test converting a UserProperty model to dict."""
        last_time = datetime.datetime(
            2024, 3, 15, 12, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=9))
        )
        next_time = last_time + datetime.timedelta(hours=1)  # Next time is 1 hour later
        user_property_data = {
            "line_user_id": "U1234567890abcdef1234567890abcdef",
            "property_id": str(ObjectId()),
            "last_aggregated_at": last_time,
            "next_aggregated_at": next_time,
        }
        user_property_obj = UserProperty(**user_property_data)
        result = convert_to_dict(user_property_obj, "user_properties")

        assert isinstance(result, dict)
        assert "id" not in result  # Should exclude id field
        assert result["line_user_id"] == user_property_data["line_user_id"]
        assert result["property_id"] == user_property_data["property_id"]
        assert result["last_aggregated_at"] == last_time
        assert result["next_aggregated_at"] == next_time

    def test_convert_dict_to_dict(self):
        """Test converting a dict to dict."""
        data = {"key": "value"}
        result = convert_to_dict(data, "test")
        assert result == data

    def test_convert_invalid_type(self):
        """Test converting an invalid type."""
        result = convert_to_dict(123, "test")  # type: ignore
        assert result == {}


class TestEnsureObjectId:
    def test_ensure_object_id_with_string(self):
        """Test converting string to ObjectId."""
        obj_id = ObjectId()
        result = ensure_object_id(str(obj_id))
        assert isinstance(result, ObjectId)
        assert result == obj_id

    def test_ensure_object_id_with_object_id(self):
        """Test passing ObjectId directly."""
        obj_id = ObjectId()
        result = ensure_object_id(obj_id)
        assert result == obj_id

    def test_ensure_object_id_with_none(self):
        """Test handling None value."""
        result = ensure_object_id(None)
        assert result is None

    def test_ensure_object_id_with_invalid_string(self):
        """Test handling invalid ObjectId string."""
        result = ensure_object_id("invalid")
        assert result is None


class TestMongoPipeline:
    @pytest.fixture
    def pipeline(self):
        """Create a MongoPipeline instance."""
        crawler = Mock()
        crawler.settings = {
            "MONGO_URI": "mongodb://localhost:27017",
            "MONGO_DATABASE": "test_db",
            "IMAGES_STORE": "tmp/images",
            "GCP_BUCKET_NAME": "test-bucket",
            "GCP_FOLDER_NAME": "test-folder",
        }
        pipeline = MongoPipeline.from_crawler(crawler)
        return pipeline

    @pytest.fixture
    def mock_db(self):
        """Create a mock MongoDB database."""
        with patch("pymongo.MongoClient") as mock_client:
            mock_db = MagicMock()
            mock_client.return_value.__getitem__.return_value = mock_db
            yield mock_db

    def test_process_item_success(self, pipeline, mock_db):
        """Test successful item processing."""
        # Setup
        pipeline.db = mock_db
        current_time = "2024-03-15T12:00:00+09:00"
        item = {
            "properties": Property(
                name="Test Property",
                url="https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_95982188/",
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
            )
        }

        # Test
        result = pipeline.process_item(item, None)

        # Verify
        assert result == item
        mock_db["properties"].find_one.assert_called_once()

    def test_process_item_no_property(self, pipeline, mock_db):
        """Test processing item without property data."""
        # Setup
        pipeline.db = mock_db
        item = {}

        # Test
        result = pipeline.process_item(item, None)

        # Verify
        assert result == item
        mock_db["properties"].find_one.assert_not_called()

    def test_process_item_error(self, pipeline, mock_db):
        """Test error handling during item processing."""
        # Setup
        pipeline.db = mock_db
        mock_db["properties"].find_one.side_effect = Exception("Database error")
        current_time = "2024-03-15T12:00:00+09:00"
        item = {
            "properties": Property(
                name="Test Property",
                url="https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_95982188/",
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
            )
        }

        # Test
        with pytest.raises(DropItem):
            pipeline.process_item(item, None)


@pytest.fixture
def pipeline():
    """Create a SuumoImagesPipeline instance."""
    settings = Settings(
        {
            "IMAGES_STORE": "tmp/images",
            "GCP_BUCKET_NAME": "mansion_watch",
            "GCP_FOLDER_NAME": "property_images",
            "MONGO_URI": "mongodb://localhost:27017",
            "MONGO_DATABASE": "mansion_watch",
        }
    )
    crawler = Mock()
    crawler.settings = settings

    # Mock GCP credentials and storage
    with patch.dict(
        os.environ,
        {
            "GOOGLE_APPLICATION_CREDENTIALS": "service-account.json",
            "GCP_PROJECT_ID": "test-project",
            "GCS_IMAGE_QUALITY": "30",
        },
    ), patch("os.path.exists", return_value=True), patch(
        "google.cloud.storage.Client"
    ) as mock_gcs_client:
        mock_bucket = Mock()
        mock_bucket.exists.return_value = True
        mock_gcs_client.return_value.bucket.return_value = mock_bucket

        pipeline = SuumoImagesPipeline.from_crawler(crawler)
        pipeline.open_spider(
            Mock(settings=settings)
        )  # Call open_spider to initialize attributes
        pipeline.storage_client = mock_gcs_client.return_value
        pipeline.bucket = mock_bucket
        pipeline.logger = logging.getLogger(__name__)
        return pipeline


class TestSuumoImagesPipeline:
    """Test cases for SuumoImagesPipeline."""

    def test_file_path(self, pipeline):
        """Test file path generation."""
        request = Mock()
        request.url = "https://example.com/image.jpg"
        request.meta = {"property_id": "123"}

        path = pipeline.file_path(request)
        assert path == "image.jpg"

    def test_get_media_requests(self, pipeline):
        """Test media requests generation."""
        current_time = datetime.datetime.now(datetime.timezone.utc)
        item = {
            os.getenv("COLLECTION_PROPERTIES", "properties"): Property(
                name="Test Property",
                url="https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_95982188/",
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
                image_urls=[
                    "https://example.com/image1.jpg",
                    "https://example.com/image2.jpg",
                ],
            )
        }
        # Mock check_blob_exists to return False
        with patch(
            "mansion_watch_scraper.pipelines.check_blob_exists", return_value=False
        ):
            requests = list(pipeline.get_media_requests(item, Mock()))
            assert len(requests) == 2
            assert all(isinstance(r, scrapy.Request) for r in requests)
            assert requests[0].url == "https://example.com/image1.jpg"
            assert requests[1].url == "https://example.com/image2.jpg"

    def test_get_media_requests_no_images(self, pipeline):
        """Test media requests generation with no images."""
        current_time = datetime.datetime.now(datetime.timezone.utc)
        item = {
            "properties": Property(
                name="Test Property",
                url="https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_95982188/",
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
                image_urls=[],
            )
        }
        requests = list(pipeline.get_media_requests(item, Mock()))
        assert len(requests) == 0


def test_process_image(mock_image):
    """Test image processing function."""
    # Create a temporary file
    with open("test_image.jpg", "wb") as f:
        f.write(mock_image.getvalue())

    try:
        # Process the image
        result = process_image("test_image.jpg")

        # Verify
        assert isinstance(result, io.BytesIO)

        # Check if the processed image can be opened
        img = Image.open(result)
        assert img.format == "JPEG"
        assert img.mode == "RGB"
    finally:
        # Cleanup
        os.remove("test_image.jpg")


def test_upload_to_gcs(mock_bucket, mock_image):
    """Test GCS upload function."""
    # Setup
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    # Create a temporary file
    with open("test_image.jpg", "wb") as f:
        f.write(mock_image.getvalue())

    try:
        # Test
        result = upload_to_gcs(mock_bucket, "test_image.jpg", "test/image.jpg")

        # Verify
        assert result is True
        mock_bucket.blob.assert_called_once_with("test/image.jpg")
        mock_blob.upload_from_file.assert_called_once()
    finally:
        # Cleanup
        os.remove("test_image.jpg")
