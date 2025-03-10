from unittest.mock import MagicMock, patch

import pytest
from scrapy.http import Request, Response
from twisted.internet.error import DNSLookupError, TCPTimedOutError, TimeoutError

from mansion_watch_scraper.spiders.suumo_scraper import MansionWatchSpider


class TestMansionWatchSpider:
    @pytest.fixture
    def spider(self):
        """Create a spider instance for testing."""
        return MansionWatchSpider(
            url="https://example.com", line_user_id="Utest_user_id"
        )

    def test_process_hidden_input_url(self, spider):
        """Test processing of hidden input URLs."""
        # Test with valid URL
        url = "https://example.com?src=path/to/image.jpg&other=param"
        result = spider._process_hidden_input_url(url)
        assert result == "https://img01.suumo.com/path/to/image.jpg"

        # Test with relative URL
        url = "https://example.com?src=/images/property.jpg&other=param"
        result = spider._process_hidden_input_url(url)
        assert result == "https://img01.suumo.com/images/property.jpg"

        # Test with invalid URL
        url = "https://example.com/invalid"
        result = spider._process_hidden_input_url(url)
        assert result is None

    def test_process_lightbox_url(self, spider):
        """Test processing of lightbox gallery URLs."""
        # Test with relative URL
        url = "/images/property.jpg"
        result = spider._process_lightbox_url(url)
        assert result == "https://suumo.jp/images/property.jpg"

        # Test with absolute URL
        url = "https://suumo.jp/images/property.jpg"
        result = spider._process_lightbox_url(url)
        assert result == url

    def test_process_image_urls(self, spider):
        """Test processing of mixed image URLs."""
        # Test with mixed URLs
        urls = [
            "https://example.com/spacer.gif",  # Should be skipped
            "https://example.com?src=property1.jpg",  # Hidden input
            "https://example.com?src=property2.jpg",  # Hidden input (duplicate)
            "/images/property3.jpg",  # Lightbox
            "https://suumo.jp/images/property4.jpg",  # Lightbox (absolute)
        ]

        result = spider._process_image_urls(urls)
        assert len(result) == 4
        assert "https://img01.suumo.com/property1.jpg" in result
        assert "https://img01.suumo.com/property2.jpg" in result
        assert "https://suumo.jp/images/property3.jpg" in result
        assert "https://suumo.jp/images/property4.jpg" in result

    @patch("mansion_watch_scraper.spiders.suumo_scraper.MansionWatchSpider.logger")
    def test_errback_httpbin_404(self, mock_logger, spider):
        """Test the errback_httpbin method with a 404 error."""
        # Create a mock response with a 404 status
        mock_response = MagicMock(spec=Response)
        mock_response.status = 404
        mock_response.url = "https://example.com/not_found"

        # Create a mock failure with an HttpError
        mock_failure = MagicMock()
        mock_failure.check.return_value = (
            True  # This will make failure.check(HttpError) return True
        )
        mock_failure.value.response = mock_response

        # Call the errback method
        spider.errback_httpbin(mock_failure)

        # Check that the logger was called with the correct messages at the INFO level
        mock_logger.info.assert_any_call("HttpError on %s", mock_response.url)
        mock_logger.info.assert_any_call("HTTP Status Code: %s", mock_response.status)
        mock_logger.info.assert_any_call(
            "Property not found (404). The URL may be incorrect or the property listing may have been removed."
        )

    @patch("mansion_watch_scraper.spiders.suumo_scraper.MansionWatchSpider.logger")
    def test_errback_httpbin_403(self, mock_logger, spider):
        """Test the errback_httpbin method with a 403 error."""
        # Create a mock response with a 403 status
        mock_response = MagicMock(spec=Response)
        mock_response.status = 403
        mock_response.url = "https://example.com/forbidden"

        # Create a mock failure with an HttpError
        mock_failure = MagicMock()
        mock_failure.check.return_value = (
            True  # This will make failure.check(HttpError) return True
        )
        mock_failure.value.response = mock_response

        # Call the errback method
        spider.errback_httpbin(mock_failure)

        # Check that the logger was called with the correct messages at the ERROR level
        mock_logger.error.assert_any_call("HttpError on %s", mock_response.url)
        mock_logger.error.assert_any_call("HTTP Status Code: %s", mock_response.status)
        mock_logger.error.assert_any_call(
            "Access forbidden (403). The site may be blocking scrapers."
        )

    @patch("mansion_watch_scraper.spiders.suumo_scraper.MansionWatchSpider.logger")
    def test_errback_httpbin_500(self, mock_logger, spider):
        """Test the errback_httpbin method with a 500 error."""
        # Create a mock response with a 500 status
        mock_response = MagicMock(spec=Response)
        mock_response.status = 500
        mock_response.url = "https://example.com/server_error"

        # Create a mock failure with an HttpError
        mock_failure = MagicMock()
        mock_failure.check.return_value = (
            True  # This will make failure.check(HttpError) return True
        )
        mock_failure.value.response = mock_response

        # Call the errback method
        spider.errback_httpbin(mock_failure)

        # Check that the logger was called with the correct messages at the ERROR level
        mock_logger.error.assert_any_call("HttpError on %s", mock_response.url)
        mock_logger.error.assert_any_call("HTTP Status Code: %s", mock_response.status)
        mock_logger.error.assert_any_call(
            "Server error (500). The property site is experiencing issues."
        )

    @patch("mansion_watch_scraper.spiders.suumo_scraper.MansionWatchSpider.logger")
    def test_errback_httpbin_dns_lookup_error(self, mock_logger, spider):
        """Test the errback_httpbin method with a DNSLookupError."""
        # Create a mock request
        mock_request = MagicMock(spec=Request)
        mock_request.url = "https://nonexistent.example.com"

        # Create a mock failure with a DNSLookupError
        mock_failure = MagicMock()
        mock_failure.check.side_effect = lambda error_type: error_type == DNSLookupError
        mock_failure.request = mock_request

        # Call the errback method
        spider.errback_httpbin(mock_failure)

        # Check that the logger was called with the correct messages
        mock_logger.error.assert_any_call("DNSLookupError on %s", mock_request.url)
        mock_logger.error.assert_any_call(
            "Could not resolve domain name. Check internet connection or if the domain exists."
        )

    @patch("mansion_watch_scraper.spiders.suumo_scraper.MansionWatchSpider.logger")
    def test_errback_httpbin_timeout_error(self, mock_logger, spider):
        """Test the errback_httpbin method with a TimeoutError."""
        # Create a mock request
        mock_request = MagicMock(spec=Request)
        mock_request.url = "https://slow.example.com"

        # Create a mock failure with a TimeoutError
        mock_failure = MagicMock()
        mock_failure.check.side_effect = (
            lambda *error_types: TimeoutError in error_types
            or TCPTimedOutError in error_types
        )
        mock_failure.request = mock_request

        # Call the errback method
        spider.errback_httpbin(mock_failure)

        # Check that the logger was called with the correct messages
        mock_logger.error.assert_any_call("TimeoutError on %s", mock_request.url)
        mock_logger.error.assert_any_call(
            "Request timed out. The server may be slow or unresponsive."
        )
