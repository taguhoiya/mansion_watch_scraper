import datetime
import io
import logging
import os
import tempfile
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
    CommonOverview,
    MongoPipeline,
    ProcessedImage,
    PropertyOverview,
    SuumoImagesPipeline,
    check_blob_exists,
    convert_to_dict,
    create_image_request,
    download_image,
    ensure_object_id,
    get_gcs_url,
    process_image,
    process_image_file,
    upload_to_gcs,
    validate_response,
)

# Test data
TEST_MONGO_URI = "mongodb://localhost:27017"
TEST_MONGO_DB = "test_db"
TEST_IMAGES_STORE = "test_images"
TEST_GCP_BUCKET = "test_bucket"
TEST_GCP_FOLDER = "test_folder"
TEST_SUUMO_URL = "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_95982188/"


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
        current_time = datetime.datetime.now(datetime.timezone.utc)
        property_obj = Property(
            name="Test Property",
            url=TEST_SUUMO_URL,
            is_active=True,
            created_at=current_time,
            updated_at=current_time,
        )
        result = convert_to_dict(property_obj, "properties")
        assert isinstance(result, dict)
        assert result["name"] == "Test Property"
        assert result["is_active"] is True

    def test_convert_user_property_to_dict(self):
        """Test converting a UserProperty model to dict."""
        current_time = datetime.datetime.now(datetime.timezone.utc)
        next_time = current_time + datetime.timedelta(days=3)
        user_property = UserProperty(
            line_user_id="U1234567890",
            property_id=str(ObjectId()),
            last_aggregated_at=current_time,
            next_aggregated_at=next_time,
        )
        result = convert_to_dict(user_property, "user_properties")
        assert isinstance(result, dict)
        assert result["line_user_id"] == "U1234567890"

    def test_convert_dict_to_dict(self):
        """Test converting a dict to dict."""
        data = {"key": "value"}
        result = convert_to_dict(data, "test")
        assert result == data

    def test_convert_invalid_type(self):
        """Test converting an invalid type."""
        result = convert_to_dict(123, "test")
        assert result == {}


class TestEnsureObjectId:
    def test_ensure_object_id_with_string(self):
        """Test converting string to ObjectId."""
        test_id = str(ObjectId())
        result = ensure_object_id(test_id)
        assert isinstance(result, ObjectId)
        assert str(result) == test_id

    def test_ensure_object_id_with_object_id(self):
        """Test passing ObjectId directly."""
        test_id = ObjectId()
        result = ensure_object_id(test_id)
        assert result == test_id

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
        settings = Settings()
        settings.setdict(
            {
                "MONGO_URI": TEST_MONGO_URI,
                "MONGO_DATABASE": TEST_MONGO_DB,
                "IMAGES_STORE": TEST_IMAGES_STORE,
                "GCP_BUCKET_NAME": TEST_GCP_BUCKET,
                "GCP_FOLDER_NAME": TEST_GCP_FOLDER,
                "PUBSUB_TOPIC": "test-topic",
                "PUBSUB_SUBSCRIPTION": "test-subscription",
                "GCP_PROJECT_ID": "test-project",
            }
        )
        return MongoPipeline.from_crawler(Mock(settings=settings))

    @pytest.fixture
    def mock_db(self):
        """Create a mock MongoDB database."""
        mock = MagicMock()
        return mock

    def test_process_item_success(self, pipeline, mock_db):
        """Test successful item processing."""
        pipeline.db = mock_db
        current_time = datetime.datetime.now(datetime.timezone.utc)
        item = {
            "properties": Property(
                name="Test Property",
                url=TEST_SUUMO_URL,
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
            )
        }
        result = pipeline.process_item(item, None)
        assert result == item

    def test_process_item_no_property(self, pipeline, mock_db):
        """Test processing item without property."""
        pipeline.db = mock_db
        item = {"other_data": "test"}
        result = pipeline.process_item(item, None)
        assert result == item

    def test_process_item_error(self, pipeline, mock_db):
        """Test error handling during item processing."""
        pipeline.db = mock_db
        # Mock find_one to return None to force insert_one to be called
        mock_db["properties"].find_one.return_value = None
        # Set up insert_one to raise an exception
        mock_db["properties"].insert_one.side_effect = Exception("Test error")
        current_time = datetime.datetime.now(datetime.timezone.utc)
        item = {
            "properties": Property(
                name="Test Property",
                url=TEST_SUUMO_URL,
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
            )
        }

        with pytest.raises(DropItem):
            pipeline.process_item(item, None)

    def test_process_item_update_existing(self, pipeline, mock_db):
        """Test updating an existing property document."""
        pipeline.db = mock_db
        existing_id = ObjectId()
        current_time = datetime.datetime.now(datetime.timezone.utc)
        old_time = current_time - datetime.timedelta(days=1)

        # Mock existing document
        mock_db["properties"].find_one.return_value = {
            "_id": existing_id,
            "name": "Old Name",
            "url": TEST_SUUMO_URL,
            "is_active": True,
            "created_at": old_time,
            "updated_at": old_time,
        }

        # New item with updated data
        item = {
            "properties": Property(
                name="New Name",
                url=TEST_SUUMO_URL,
                is_active=False,
                created_at=current_time,
                updated_at=current_time,
            )
        }

        # Test
        result = pipeline.process_item(item, None)

        # Verify
        assert result == item
        mock_db["properties"].find_one.assert_called_once()
        mock_db["properties"].update_one.assert_called_once()

        # Verify that _id and created_at are not included in the update
        update_dict = mock_db["properties"].update_one.call_args[0][1]["$set"]
        assert "_id" not in update_dict
        assert "created_at" not in update_dict
        assert update_dict["name"] == "New Name"
        assert update_dict["is_active"] is False
        assert update_dict["updated_at"] == current_time

    def test_process_item_insert_new(self, pipeline, mock_db):
        """Test inserting a new property document."""
        pipeline.db = mock_db
        new_id = ObjectId()
        current_time = datetime.datetime.now(datetime.timezone.utc)

        # Mock find_one to return None (no existing document)
        mock_db["properties"].find_one.return_value = None
        # Mock insert_one to return a result with the new _id
        mock_db["properties"].insert_one.return_value = MagicMock(inserted_id=new_id)

        # New item to insert
        item = {
            "properties": Property(
                name="Test Property",
                url=TEST_SUUMO_URL,
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
        mock_db["properties"].insert_one.assert_called_once()

    def test_process_user_property_update_existing(self, pipeline, mock_db):
        """Test updating an existing user property document."""
        pipeline.db = mock_db
        existing_id = ObjectId()
        property_id = ObjectId()
        current_time = datetime.datetime.now(datetime.timezone.utc)
        old_time = current_time - datetime.timedelta(days=1)
        next_time = current_time + datetime.timedelta(days=3)

        # Create separate mock objects for each collection
        properties_collection = MagicMock()
        user_properties_collection = MagicMock()
        mock_db.__getitem__.side_effect = lambda x: {
            "properties": properties_collection,
            "user_properties": user_properties_collection,
        }[x]

        # Mock property processing first
        properties_collection.find_one.return_value = {
            "_id": property_id,
            "name": "Test Property",
            "url": TEST_SUUMO_URL,
            "is_active": True,
            "created_at": old_time,
            "updated_at": old_time,
        }

        # Mock existing user property document
        user_properties_collection.find_one.return_value = {
            "_id": existing_id,
            "line_user_id": "U1234567890",
            "property_id": str(property_id),
            "created_at": old_time,
            "first_succeeded_at": old_time,
            "last_succeeded_at": old_time,
            "last_aggregated_at": old_time,
            "next_aggregated_at": current_time,
        }

        # New item with updated data
        item = {
            "properties": Property(
                name="Test Property",
                url=TEST_SUUMO_URL,
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
            ),
            "user_properties": UserProperty(
                line_user_id="U1234567890",
                property_id=str(property_id),
                last_aggregated_at=current_time,
                next_aggregated_at=next_time,
            ),
        }

        # Test
        result = pipeline.process_item(item, None)

        # Verify
        assert result == item
        properties_collection.find_one.assert_called_once()
        user_properties_collection.find_one.assert_called_once()
        user_properties_collection.update_one.assert_called_once()

    def test_process_user_property_insert_new(self, pipeline, mock_db):
        """Test inserting a new user property document."""
        pipeline.db = mock_db
        new_id = ObjectId()
        property_id = ObjectId()
        current_time = datetime.datetime.now(datetime.timezone.utc)
        next_time = current_time + datetime.timedelta(days=3)

        # Create separate mock objects for each collection
        properties_collection = MagicMock()
        user_properties_collection = MagicMock()
        mock_db.__getitem__.side_effect = lambda x: {
            "properties": properties_collection,
            "user_properties": user_properties_collection,
        }[x]

        # Mock property processing first
        properties_collection.find_one.return_value = {
            "_id": property_id,
            "name": "Test Property",
            "url": TEST_SUUMO_URL,
            "is_active": True,
            "created_at": current_time,
            "updated_at": current_time,
        }

        # Mock find_one to return None (no existing document)
        user_properties_collection.find_one.return_value = None
        # Mock insert_one to return a result with the new _id
        user_properties_collection.insert_one.return_value = MagicMock(
            inserted_id=new_id
        )

        # New item to insert
        item = {
            "properties": Property(
                name="Test Property",
                url=TEST_SUUMO_URL,
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
            ),
            "user_properties": UserProperty(
                line_user_id="U1234567890",
                property_id=str(property_id),
                last_aggregated_at=current_time,
                next_aggregated_at=next_time,
            ),
        }

        # Test
        result = pipeline.process_item(item, None)

        # Verify
        assert result == item
        properties_collection.find_one.assert_called_once()
        user_properties_collection.find_one.assert_called_once()
        user_properties_collection.insert_one.assert_called_once()

    def test_process_common_overview_update_existing(self, pipeline, mock_db):
        """Test updating an existing common overview document."""
        pipeline.db = mock_db
        existing_id = ObjectId()
        property_id = ObjectId()
        current_time = datetime.datetime.now(datetime.timezone.utc)

        # Create separate mock objects for each collection
        properties_collection = MagicMock()
        common_overviews_collection = MagicMock()
        mock_db.__getitem__.side_effect = lambda x: {
            "properties": properties_collection,
            "common_overviews": common_overviews_collection,
        }[x]

        # Mock property processing first
        properties_collection.find_one.return_value = {
            "_id": property_id,
            "name": "Test Property",
            "url": TEST_SUUMO_URL,
            "is_active": True,
            "created_at": current_time,
            "updated_at": current_time,
        }

        # Mock existing document
        common_overviews_collection.find_one.return_value = {
            "_id": existing_id,
            "property_id": str(property_id),
            "location": "東京都渋谷区",
            "transportation": ["渋谷駅徒歩5分"],
            "total_units": "10戸",
            "structure_floors": "RC3階建",
            "site_area": "100㎡",
            "site_ownership_type": "所有権",
            "usage_area": "第一種住居地域",
            "parking_lot": "有",
            "created_at": current_time,
            "updated_at": current_time,
        }

        # New item with updated data
        item = {
            "properties": Property(
                name="Test Property",
                url=TEST_SUUMO_URL,
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
            ),
            "common_overviews": CommonOverview(
                property_id=str(property_id),
                location="東京都新宿区",
                transportation=["新宿駅徒歩3分"],
                total_units="12戸",
                structure_floors="RC4階建",
                site_area="120㎡",
                site_ownership_type="所有権",
                usage_area="第一種住居地域",
                parking_lot="有",
                created_at=current_time,
                updated_at=current_time,
            ),
        }

        # Test
        result = pipeline.process_item(item, None)

        # Verify
        assert result == item
        properties_collection.find_one.assert_called_once()
        common_overviews_collection.find_one.assert_called_once()
        common_overviews_collection.update_one.assert_called_once()

    def test_process_common_overview_insert_new(self, pipeline, mock_db):
        """Test inserting a new common overview document."""
        pipeline.db = mock_db
        new_id = ObjectId()
        property_id = ObjectId()
        current_time = datetime.datetime.now(datetime.timezone.utc)

        # Create separate mock objects for each collection
        properties_collection = MagicMock()
        common_overviews_collection = MagicMock()
        mock_db.__getitem__.side_effect = lambda x: {
            "properties": properties_collection,
            "common_overviews": common_overviews_collection,
        }[x]

        # Mock property processing first
        properties_collection.find_one.return_value = {
            "_id": property_id,
            "name": "Test Property",
            "url": TEST_SUUMO_URL,
            "is_active": True,
            "created_at": current_time,
            "updated_at": current_time,
        }

        # Mock find_one to return None (no existing document)
        common_overviews_collection.find_one.return_value = None
        # Mock insert_one to return a result with the new _id
        common_overviews_collection.insert_one.return_value = MagicMock(
            inserted_id=new_id
        )

        # New item to insert
        item = {
            "properties": Property(
                name="Test Property",
                url=TEST_SUUMO_URL,
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
            ),
            "common_overviews": CommonOverview(
                property_id=str(property_id),
                location="東京都新宿区",
                transportation=["新宿駅徒歩3分"],
                total_units="12戸",
                structure_floors="RC4階建",
                site_area="120㎡",
                site_ownership_type="所有権",
                usage_area="第一種住居地域",
                parking_lot="有",
                created_at=current_time,
                updated_at=current_time,
            ),
        }

        # Test
        result = pipeline.process_item(item, None)

        # Verify
        assert result == item
        properties_collection.find_one.assert_called_once()
        common_overviews_collection.find_one.assert_called_once()
        common_overviews_collection.insert_one.assert_called_once()

    def test_process_property_overview_update_existing(self, pipeline, mock_db):
        """Test updating an existing property overview document."""
        pipeline.db = mock_db
        existing_id = ObjectId()
        property_id = ObjectId()
        current_time = datetime.datetime.now(datetime.timezone.utc)

        # Create separate mock objects for each collection
        properties_collection = MagicMock()
        property_overviews_collection = MagicMock()
        mock_db.__getitem__.side_effect = lambda x: {
            "properties": properties_collection,
            "property_overviews": property_overviews_collection,
        }[x]

        # Mock property processing first
        properties_collection.find_one.return_value = {
            "_id": property_id,
            "name": "Test Property",
            "url": TEST_SUUMO_URL,
            "is_active": True,
            "created_at": current_time,
            "updated_at": current_time,
        }

        # Mock existing document
        property_overviews_collection.find_one.return_value = {
            "_id": existing_id,
            "property_id": str(property_id),
            "sales_schedule": "-",
            "event_information": "-",
            "number_of_units_for_sale": "1戸",
            "highest_price_range": "-",
            "price": "5000万円",
            "maintenance_fee": "10000円/月",
            "repair_reserve_fund": "15000円/月",
            "first_repair_reserve_fund": "-",
            "other_expenses": "-",
            "floor_plan": "3LDK",
            "area": "75㎡",
            "other_area": "-",
            "delivery_time": "即入居可",
            "completion_time": "2020年3月",
            "floor": "3階",
            "direction": "南",
            "energy_consumption_performance": "-",
            "insulation_performance": "-",
            "estimated_utility_cost": "-",
            "renovation": "-",
            "other_restrictions": "-",
            "other_overview_and_special_notes": "-",
            "created_at": current_time,
            "updated_at": current_time,
        }

        # New item with updated data
        item = {
            "properties": Property(
                name="Test Property",
                url=TEST_SUUMO_URL,
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
            ),
            "property_overviews": PropertyOverview(
                property_id=str(property_id),
                sales_schedule="-",
                event_information="-",
                number_of_units_for_sale="1戸",
                highest_price_range="-",
                price="5500万円",
                maintenance_fee="12000円/月",
                repair_reserve_fund="18000円/月",
                first_repair_reserve_fund="-",
                other_expenses="-",
                floor_plan="4LDK",
                area="85㎡",
                other_area="-",
                delivery_time="即入居可",
                completion_time="2020年3月",
                floor="4階",
                direction="南東",
                energy_consumption_performance="-",
                insulation_performance="-",
                estimated_utility_cost="-",
                renovation="-",
                other_restrictions="-",
                other_overview_and_special_notes="-",
                created_at=current_time,
                updated_at=current_time,
            ),
        }

        # Test
        result = pipeline.process_item(item, None)

        # Verify
        assert result == item
        properties_collection.find_one.assert_called_once()
        property_overviews_collection.find_one.assert_called_once()
        property_overviews_collection.update_one.assert_called_once()

    def test_process_property_overview_insert_new(self, pipeline, mock_db):
        """Test inserting a new property overview document."""
        pipeline.db = mock_db
        new_id = ObjectId()
        property_id = ObjectId()
        current_time = datetime.datetime.now(datetime.timezone.utc)

        # Create separate mock objects for each collection
        properties_collection = MagicMock()
        property_overviews_collection = MagicMock()
        mock_db.__getitem__.side_effect = lambda x: {
            "properties": properties_collection,
            "property_overviews": property_overviews_collection,
        }[x]

        # Mock property processing first
        properties_collection.find_one.return_value = {
            "_id": property_id,
            "name": "Test Property",
            "url": TEST_SUUMO_URL,
            "is_active": True,
            "created_at": current_time,
            "updated_at": current_time,
        }

        # Mock find_one to return None (no existing document)
        property_overviews_collection.find_one.return_value = None
        # Mock insert_one to return a result with the new _id
        property_overviews_collection.insert_one.return_value = MagicMock(
            inserted_id=new_id
        )

        # New item to insert
        item = {
            "properties": Property(
                name="Test Property",
                url=TEST_SUUMO_URL,
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
            ),
            "property_overviews": PropertyOverview(
                property_id=str(property_id),
                sales_schedule="-",
                event_information="-",
                number_of_units_for_sale="1戸",
                highest_price_range="-",
                price="5000万円",
                maintenance_fee="10000円/月",
                repair_reserve_fund="15000円/月",
                first_repair_reserve_fund="-",
                other_expenses="-",
                floor_plan="3LDK",
                area="75㎡",
                other_area="-",
                delivery_time="即入居可",
                completion_time="2020年3月",
                floor="3階",
                direction="南",
                energy_consumption_performance="-",
                insulation_performance="-",
                estimated_utility_cost="-",
                renovation="-",
                other_restrictions="-",
                other_overview_and_special_notes="-",
                created_at=current_time,
                updated_at=current_time,
            ),
        }

        # Test
        result = pipeline.process_item(item, None)

        # Verify
        assert result == item
        properties_collection.find_one.assert_called_once()
        property_overviews_collection.find_one.assert_called_once()
        property_overviews_collection.insert_one.assert_called_once()


@pytest.fixture
def pipeline():
    """Create a SuumoImagesPipeline instance."""
    settings = Settings()
    settings.setdict(
        {
            "IMAGES_STORE": TEST_IMAGES_STORE,
            "GCP_BUCKET_NAME": TEST_GCP_BUCKET,
            "GCP_FOLDER_NAME": TEST_GCP_FOLDER,
            "IMAGES_URLS_FIELD": "image_urls",
            "IMAGES_RESULT_FIELD": "images",
            "IMAGES_MIN_HEIGHT": 50,
            "IMAGES_MIN_WIDTH": 50,
            "IMAGES_STORE_FORMAT": "JPEG",
            "IMAGES_DOMAINS": ["img01.suumo.com"],
            "MONGO_URI": TEST_MONGO_URI,
            "MONGO_DATABASE": TEST_MONGO_DB,
            "PUBSUB_TOPIC": "test-topic",
            "PUBSUB_SUBSCRIPTION": "test-subscription",
            "GCP_PROJECT_ID": "test-project",
        }
    )
    crawler = Mock()
    crawler.settings = settings

    # Mock GCP credentials and storage
    with (
        patch.dict(
            os.environ,
            {
                "GOOGLE_APPLICATION_CREDENTIALS": "service-account.json",
                "GCP_PROJECT_ID": "test-project",
                "GCS_IMAGE_QUALITY": "30",
            },
        ),
        patch("os.path.exists", return_value=True),
        patch("google.cloud.storage.Client") as mock_gcs_client,
    ):
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
        # The file path includes a hash of the URL and is stored in the 'full' directory
        assert path.startswith("full/")
        assert path.endswith(".jpg")

    def test_get_media_requests(self, pipeline):
        """Test media request generation."""
        # Create a test item with image URLs
        item = {
            "image_urls": [
                "https://example.com/image1.jpg",
                "https://example.com/image2.jpg",
            ]
        }

        # Get media requests
        requests = pipeline.get_media_requests(item, None)

        # Verify
        assert len(requests) == 2
        for request in requests:
            assert isinstance(request, scrapy.Request)
            assert request.url in item["image_urls"]
            assert request.meta["download_timeout"] == 30
            assert request.headers[b"Accept"] == b"image/*"
            assert request.headers[b"Referer"] == b"https://suumo.jp/"

    def test_get_media_requests_no_images(self, pipeline):
        """Test media requests generation with no images."""
        current_time = datetime.datetime.now(datetime.timezone.utc)
        item = {
            "properties": Property(
                name="Test Property",
                url=TEST_SUUMO_URL,
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
                image_urls=[],
            )
        }
        requests = list(pipeline.get_media_requests(item, Mock()))
        assert len(requests) == 0

    def test_process_item_error_handling(self, pipeline):
        """Test error handling in process_item."""
        # Test with invalid image URLs
        item = {"image_urls": ["invalid://url.jpg"]}
        result = pipeline.process_item(item, Mock())
        assert result == item

        # Test with network error
        with patch("requests.Session") as mock_session:
            mock_session.return_value.__enter__.return_value.get.side_effect = (
                Exception("Network error")
            )
            item = {"image_urls": ["https://example.com/image.jpg"]}
            result = pipeline.process_item(item, Mock())
            assert result == item

    def test_cleanup_operations(self, pipeline):
        """Test cleanup operations."""
        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a subdirectory for images
            images_dir = os.path.join(tmp_dir, "images")
            os.makedirs(images_dir)
            pipeline.images_store = images_dir

            # Create test files
            test_files = ["test1.jpg", "test2.jpg"]
            for f in test_files:
                with open(os.path.join(images_dir, f), "w") as file:
                    file.write("test")

            # Test cleanup
            assert pipeline._cleanup_temp_directory()
            for f in test_files:
                assert not os.path.exists(os.path.join(images_dir, f))

        # Test cleanup with non-existent directory
        pipeline.images_store = "/nonexistent/path"
        assert not pipeline._cleanup_temp_directory()

    def test_open_spider_error_handling(self, pipeline):
        """Test error handling in open_spider."""
        spider = Mock()
        spider.settings = Settings(
            {
                "IMAGES_STORE": "tmp/images",
                "GCP_BUCKET_NAME": "test-bucket",
                "GCP_FOLDER_NAME": "test-folder",
                "MONGO_URI": "mongodb://localhost:27017",
                "MONGO_DATABASE": "test_db",
            }
        )

        # Test missing GCP credentials
        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(ValueError) as exc_info,
        ):
            pipeline.open_spider(spider)
        assert "Missing GCP credentials path" in str(exc_info.value)

        # Test invalid GCP credentials file
        with (
            patch.dict(
                os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": "/invalid/path.json"}
            ),
            patch("os.path.exists", return_value=False),
            pytest.raises(FileNotFoundError) as exc_info,
        ):
            pipeline.open_spider(spider)
        assert "GCP credentials file not found" in str(exc_info.value)

        # Test bucket does not exist
        with (
            patch.dict(
                os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": "service-account.json"}
            ),
            patch("os.path.exists", return_value=True),
            patch("google.cloud.storage.Client") as mock_client,
        ):
            mock_bucket = Mock()
            mock_bucket.exists.return_value = False
            mock_client.return_value.bucket.return_value = mock_bucket
            with pytest.raises(ValueError) as exc_info:
                pipeline.open_spider(spider)
            assert "does not exist" in str(exc_info.value)

    def test_item_completed_partial_success(self, pipeline):
        """Test item_completed with partial success."""
        # Setup
        current_time = datetime.datetime.now(datetime.timezone.utc)
        item = {
            "properties": Property(
                name="Test Property",
                url=TEST_SUUMO_URL,
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
                image_urls=[
                    "https://example.com/image1.jpg",
                    "https://example.com/image2.jpg",
                    "https://example.com/image3.jpg",
                ],
            )
        }

        # Mock results with mixed success/failure
        results = [
            (True, {"path": "path1.jpg", "url": "https://example.com/image1.jpg"}),
            (False, Exception("Download failed")),
            (True, {"path": "path3.jpg", "url": "https://example.com/image3.jpg"}),
        ]

        # Mock GCS upload and logger
        with (
            patch.object(pipeline, "_process_successful_downloads") as mock_process,
            patch.object(pipeline.logger, "warning") as mock_warning,
        ):
            mock_process.return_value = [
                "https://storage.googleapis.com/bucket/image1.jpg",
                "https://storage.googleapis.com/bucket/image3.jpg",
            ]

            # Mock image_url_to_gcs_url cache
            pipeline.image_url_to_gcs_url = {}

            # Test
            result = pipeline.item_completed(results, item, Mock())

            # Verify
            assert len(result["properties"].image_urls) == 2
            assert all(
                url.startswith("https://storage.googleapis.com/")
                for url in result["properties"].image_urls
            )
            mock_warning.assert_called_with("Failed to download 1 images")


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


def test_get_gcs_url():
    """Test GCS URL generation."""
    bucket_name = "test-bucket"
    blob_name = "test/image.jpg"
    expected_url = f"https://storage.googleapis.com/{bucket_name}/{blob_name}"
    assert get_gcs_url(bucket_name, blob_name) == expected_url


def test_create_image_request():
    """Test image request creation."""
    url = "https://example.com/image.jpg"
    request = create_image_request(url)
    assert request.url == url
    assert request.headers["Accept"] == "image/*"
    assert request.headers["Referer"] == "https://suumo.jp/"
    assert request.timeout == 30


def test_validate_response():
    """Test response validation."""
    # Test valid response
    valid_response = MagicMock()
    valid_response.status_code = 200
    valid_response.headers = {"Content-Type": "image/jpeg"}
    validate_response(valid_response)  # Should not raise

    # Test invalid status code
    invalid_status = MagicMock()
    invalid_status.status_code = 404
    with pytest.raises(ValueError, match="Invalid response status: 404"):
        validate_response(invalid_status)

    # Test invalid content type
    invalid_content = MagicMock()
    invalid_content.status_code = 200
    invalid_content.headers = {"Content-Type": "text/html"}
    with pytest.raises(ValueError, match="Invalid content type"):
        validate_response(invalid_content)


def test_process_image_file(mock_image):
    """Test image file processing."""
    # Create a test image file
    with open("test_image.jpg", "wb") as f:
        f.write(mock_image.getvalue())

    try:
        # Test normal case
        size = process_image_file("test_image.jpg")
        assert isinstance(size, tuple)
        assert len(size) == 2
        assert all(isinstance(x, int) for x in size)

        # Test small image
        small_img = Image.new("RGB", (40, 40))
        small_img.save("small_image.jpg")
        with pytest.raises(ValueError, match="Image too small"):
            process_image_file("small_image.jpg")

        # Test non-RGB image
        gray_img = Image.new("L", (100, 100))
        gray_img.save("gray_image.jpg")
        size = process_image_file("gray_image.jpg")
        assert isinstance(size, tuple)
        assert len(size) == 2

    finally:
        # Cleanup
        for f in ["test_image.jpg", "small_image.jpg", "gray_image.jpg"]:
            if os.path.exists(f):
                os.remove(f)


def test_download_image(mock_image):
    """Test image downloading."""
    with patch("requests.Session") as mock_session:
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.content = mock_image.getvalue()
        mock_session.return_value.__enter__.return_value.get.return_value = (
            mock_response
        )

        # Test successful download
        with tempfile.TemporaryDirectory() as tmp_dir:
            request = create_image_request("https://example.com/image.jpg")
            result = download_image(request, tmp_dir)
            assert isinstance(result, ProcessedImage)
            assert result.content_type == "image/jpeg"
            assert os.path.exists(result.path)

        # Test retry logic
        mock_session.return_value.__enter__.return_value.get.side_effect = [
            Exception("Network error"),
            mock_response,
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = download_image(request, tmp_dir)
            assert isinstance(result, ProcessedImage)

        # Test max retries exceeded
        mock_session.return_value.__enter__.return_value.get.side_effect = Exception(
            "Network error"
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = download_image(request, tmp_dir)
            assert result is None


def test_check_blob_exists(mock_bucket):
    """Test GCS blob existence check."""
    # Test existing blob
    mock_blob = MagicMock()
    mock_blob.exists.return_value = True
    mock_bucket.blob.return_value = mock_blob
    assert check_blob_exists(mock_bucket, "test/image.jpg") is True

    # Test non-existing blob
    mock_blob.exists.return_value = False
    assert check_blob_exists(mock_bucket, "test/missing.jpg") is False

    # Test error case
    mock_blob.exists.side_effect = Exception("GCS error")
    assert check_blob_exists(mock_bucket, "test/error.jpg") is False
