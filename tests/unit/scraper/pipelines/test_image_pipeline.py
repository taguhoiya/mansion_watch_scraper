import unittest
from unittest.mock import MagicMock, patch

from mansion_watch_scraper.pipelines import (
    SuumoImagesPipeline,
    check_blob_exists,
    get_gcs_url,
)


class TestImagePipeline(unittest.TestCase):
    """Test the SuumoImagesPipeline class."""

    def setUp(self):
        """Set up test fixtures."""
        self.spider = MagicMock()
        self.spider.settings.get.side_effect = lambda key: {
            "MONGO_URI": "mongodb://localhost:27017",
            "MONGO_DATABASE": "test_db",
            "IMAGES_STORE": "/tmp/images",
            "GCP_BUCKET_NAME": "test-bucket",
            "GCP_FOLDER_NAME": "test-folder",
        }.get(key)

        # Mock the storage client and bucket
        self.mock_storage_client = MagicMock()
        self.mock_bucket = MagicMock()
        self.mock_storage_client.bucket.return_value = self.mock_bucket

        # Create a patch for the storage client
        self.storage_client_patcher = patch(
            "google.cloud.storage.Client", return_value=self.mock_storage_client
        )
        self.storage_client_mock = self.storage_client_patcher.start()

        # Create the pipeline
        self.pipeline = SuumoImagesPipeline("/tmp/images")
        self.pipeline.open_spider(self.spider)

    def tearDown(self):
        """Tear down test fixtures."""
        self.storage_client_patcher.stop()

    @patch("mansion_watch_scraper.pipelines.check_blob_exists")
    def test_process_single_image_url_existing_image(self, mock_check_blob_exists):
        """Test processing a single image URL when the image already exists in GCS."""
        # Mock check_blob_exists to return True
        mock_check_blob_exists.return_value = True

        # Create a test image URL
        image_url = "https://example.com/image.jpg"
        headers = self.pipeline._get_request_headers()
        existing_images = []

        # Process the image URL
        requests = list(
            self.pipeline._process_single_image_url(image_url, headers, existing_images)
        )

        # Assert that no requests were created
        self.assertEqual(len(requests), 0)

        # Assert that the image URL was added to the cache
        self.assertIn(image_url, self.pipeline.image_url_to_gcs_url)

        # Assert that the image was added to existing_images
        self.assertEqual(len(existing_images), 1)

    @patch("mansion_watch_scraper.pipelines.check_blob_exists")
    def test_process_single_image_url_new_image(self, mock_check_blob_exists):
        """Test processing a single image URL when the image doesn't exist in GCS."""
        # Mock check_blob_exists to return False
        mock_check_blob_exists.return_value = False

        # Create a test image URL
        image_url = "https://example.com/image.jpg"
        headers = self.pipeline._get_request_headers()
        existing_images = []

        # Process the image URL
        requests = list(
            self.pipeline._process_single_image_url(image_url, headers, existing_images)
        )

        # Assert that a request was created
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url, image_url)

        # Assert that the image URL was not added to the cache
        self.assertNotIn(image_url, self.pipeline.image_url_to_gcs_url)

        # Assert that no images were added to existing_images
        self.assertEqual(len(existing_images), 0)

    def test_check_blob_exists(self):
        """Test the check_blob_exists function."""
        # Mock the blob
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        self.mock_bucket.blob.return_value = mock_blob

        # Check if a blob exists
        result = check_blob_exists(self.mock_bucket, "test-blob")

        # Assert that the result is True
        self.assertTrue(result)
        self.mock_bucket.blob.assert_called_once_with("test-blob")
        mock_blob.exists.assert_called_once()

    def test_get_gcs_url(self):
        """Test the get_gcs_url function."""
        # Get a GCS URL
        result = get_gcs_url("test-bucket", "test-blob")

        # Assert that the result is correct
        self.assertEqual(result, "gs://test-bucket/test-blob")

    @patch("mansion_watch_scraper.pipelines.check_blob_exists")
    def test_process_image_urls_with_gcs_check_chunked_logging(
        self, mock_check_blob_exists
    ):
        """Test that _process_image_urls_with_gcs_check logs existing images as a chunk."""
        # Mock check_blob_exists to return True for all images
        mock_check_blob_exists.return_value = True

        # Create test image URLs
        image_urls = [
            "https://example.com/image1.jpg",
            "https://example.com/image2.jpg",
            "https://example.com/image3.jpg",
        ]
        headers = self.pipeline._get_request_headers()

        # Mock the logger
        with patch.object(self.pipeline, "logger") as mock_logger:
            # Process the image URLs
            list(self.pipeline._process_image_urls_with_gcs_check(image_urls, headers))

            # Assert that the logger.info was called with the chunked message
            mock_logger.info.assert_any_call("3 images already exist in GCS")

            # Assert that the logger was not called with individual image messages
            for call in mock_logger.info.call_args_list:
                self.assertNotIn("Image already exists in GCS:", call[0][0])

        # Assert that all image URLs were added to the cache
        for image_url in image_urls:
            self.assertIn(image_url, self.pipeline.image_url_to_gcs_url)

    def test_log_image_processing_results_all_existing(self):
        """Test logging when all images already exist in GCS."""
        with patch.object(self.pipeline, "logger") as mock_logger:
            self.pipeline._log_image_processing_results(
                original_image_count=3,
                existing_image_count=3,
                new_gcs_urls=[],
                failed_downloads=[],
            )

            # Assert that no log was output (to avoid confusion)
            mock_logger.info.assert_not_called()

    def test_log_image_processing_results_all_new(self):
        """Test logging when all images are newly uploaded."""
        with patch.object(self.pipeline, "logger") as mock_logger:
            self.pipeline._log_image_processing_results(
                original_image_count=3,
                existing_image_count=0,
                new_gcs_urls=[
                    "gs://bucket/image1.jpg",
                    "gs://bucket/image2.jpg",
                    "gs://bucket/image3.jpg",
                ],
                failed_downloads=[],
            )

            # Assert that the correct log was output
            mock_logger.info.assert_called_once_with(
                "Updated item with 3 newly uploaded GCS image URLs"
            )

    def test_log_image_processing_results_mixed(self):
        """Test logging when some images already exist and some are newly uploaded."""
        with patch.object(self.pipeline, "logger") as mock_logger:
            self.pipeline._log_image_processing_results(
                original_image_count=5,
                existing_image_count=2,
                new_gcs_urls=[
                    "gs://bucket/image3.jpg",
                    "gs://bucket/image4.jpg",
                    "gs://bucket/image5.jpg",
                ],
                failed_downloads=[],
            )

            # Assert that the correct log was output
            mock_logger.info.assert_called_once_with(
                "Updated item with 5 GCS image URLs (2 already existed, 3 newly uploaded)"
            )

    def test_log_image_processing_results_partial(self):
        """Test logging when some images exist but others failed to process."""
        with patch.object(self.pipeline, "logger") as mock_logger:
            self.pipeline._log_image_processing_results(
                original_image_count=5,
                existing_image_count=2,
                new_gcs_urls=[],
                failed_downloads=["error1", "error2"],
            )

            # Assert that the correct log was output
            mock_logger.info.assert_called_once_with(
                "Partial update: 2 of 5 images already existed in GCS, 1 failed to process"
            )


if __name__ == "__main__":
    unittest.main()
