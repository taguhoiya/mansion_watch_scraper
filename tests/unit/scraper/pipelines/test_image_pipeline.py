import unittest
from unittest.mock import MagicMock

from mansion_watch_scraper.pipelines import SuumoImagesPipeline


class TestSuumoImagesPipeline(unittest.TestCase):
    """Test the SuumoImagesPipeline class."""

    def setUp(self):
        """Set up test fixtures."""
        self.pipeline = SuumoImagesPipeline(store_uri="file:///tmp/test_images")
        self.pipeline.logger = MagicMock()

    def test_log_image_processing_results_all_existing(self):
        """Test logging when all images already exist in GCS."""
        self.pipeline._log_image_processing_results(
            original_image_count=3,
            existing_image_count=3,
            new_gcs_urls=[],
            failed_downloads=[],
        )

        # Assert that no log was output (to avoid confusion)
        self.pipeline.logger.info.assert_not_called()

    def test_log_image_processing_results_all_new(self):
        """Test logging when all images are newly uploaded."""
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
        self.pipeline.logger.info.assert_called_once_with(
            "Updated item with 3 newly uploaded GCS image URLs"
        )

    def test_log_image_processing_results_mixed(self):
        """Test logging when some images already exist and some are newly uploaded."""
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
        self.pipeline.logger.info.assert_called_once_with(
            "(2 already existed, 3 newly uploaded)"
        )

    def test_log_image_processing_results_partial(self):
        """Test logging when some images exist but others failed to process."""
        self.pipeline._log_image_processing_results(
            original_image_count=5,
            existing_image_count=2,
            new_gcs_urls=[],
            failed_downloads=["error1", "error2"],
        )

        # Assert that the correct log was output
        self.pipeline.logger.info.assert_called_once_with(
            "Partial update: 2 of 5 images already existed in GCS, 3 failed to process"
        )


if __name__ == "__main__":
    unittest.main()
