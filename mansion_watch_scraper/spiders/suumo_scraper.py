import json
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import scrapy
from bson.objectid import ObjectId
from dotenv import load_dotenv
from scrapy.http import Response

from app.models.common_overview import COMMON_OVERVIEW_TRANSLATION_MAP, CommonOverview
from app.models.property import Property
from app.models.property_overview import (
    PROPERTY_OVERVIEW_TRANSLATION_MAP,
    PropertyOverview,
)
from app.services.utils import translate_keys
from enums.html_element_keys import ElementKeys

load_dotenv()


class MansionWatchSpider(scrapy.Spider):
    """Spider for scraping mansion property details from SUUMO website."""

    name = "mansion_watch_scraper"
    allowed_domains = ["suumo.jp"]
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "COOKIES_ENABLED": False,
        "DOWNLOAD_TIMEOUT": 120,
        "RETRY_ENABLED": True,  # Enable retries
        "RETRY_TIMES": 3,  # Try up to 3 times
        "RETRY_HTTP_CODES": [
            500,
            502,
            503,
            504,
            408,
            429,
        ],  # Retry on these status codes
        "CONCURRENT_REQUESTS": 1,
        "DOWNLOAD_DELAY": 0,
        "CLOSESPIDER_PAGECOUNT": 1,
        "LOG_ENABLED": True,
        "LOG_LEVEL": "WARNING",
        "LOG_STDOUT": False,
        "LOG_FILE": None,
        "LOG_SPIDER_OPENED": False,
        "LOG_SPIDER_CLOSED": False,
        "LOG_SCRAPED_ITEMS": False,
        "LOG_STATS": False,
        "LOG_DUPEFILTER": False,
        "STATS_DUMP": False,
        "EXTENSIONS": {},
        "EXTENSIONS_BASE": {},
        "TELNETCONSOLE_ENABLED": False,
        "FEED_EXPORT_ENABLED": False,
        "FEED_STORAGES": {},
        "FEED_EXPORTERS": {},
        "FEED_EXPORT_BATCH_ITEM_COUNT": 0,
        "LOGSTATS_INTERVAL": 0,
        "ITEM_PIPELINES": {
            "mansion_watch_scraper.pipelines.MongoPipeline": 300,
            "mansion_watch_scraper.pipelines.SuumoImagesPipeline": 1,
        },
    }

    def __init__(
        self,
        url: Optional[str] = None,
        line_user_id: Optional[str] = None,
        check_only: bool = False,
        *args,
        **kwargs,
    ):
        """Initialize the spider with URL and user ID."""
        super(MansionWatchSpider, self).__init__(*args, **kwargs)
        if url is not None:
            self.start_urls = [url]
        else:
            self.start_urls = []

        if line_user_id is not None:
            if not line_user_id.startswith("U"):
                raise ValueError("line_user_id must start with U")
            self.line_user_id = line_user_id
        if not line_user_id or not url:
            raise ValueError(
                f"Both url and line_user_id are required. url: {url}, line_user_id: {line_user_id}"
            )
        self.check_only = check_only
        self.results = {}

        # Configure spider settings based on check_only mode
        if check_only:
            self.custom_settings["ITEM_PIPELINES"] = {}
        else:
            self.custom_settings["ITEM_PIPELINES"] = {
                "mansion_watch_scraper.pipelines.MongoPipeline": 300,
                "mansion_watch_scraper.pipelines.SuumoImagesPipeline": 1,
            }

    def start_requests(self):
        """Start the scraping requests with error handling."""
        for url in self.start_urls:
            self.logger.info(f"Making request to URL: {url}")
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                dont_filter=True,
                meta={
                    "original_url": url,
                    "dont_retry": False,
                    "handle_httpstatus_list": [404, 403, 500],
                },
                errback=self.errback_httpbin,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
            )

    def errback_httpbin(self, failure):
        """Handle request failures."""
        error_type = failure.type.__name__
        error_msg = str(failure.value)
        url = failure.request.url

        self.logger.error(f"Request failed for URL {url}: {error_type} - {error_msg}")

        if hasattr(failure.value, "response") and failure.value.response is not None:
            status = failure.value.response.status
            if status == 404:
                error_msg = "Property not found (404). The URL may be incorrect or the property listing may have been removed."
            elif status == 403:
                error_msg = "Access forbidden (403). The site may be blocking scrapers."
            elif status == 500:
                error_msg = (
                    "Server error (500). The property site is experiencing issues."
                )
            self.logger.error(f"HTTP Status Code: {status}")
            self.logger.error(error_msg)

        self.results = {
            "status": "error",
            "error_type": error_type,
            "error_message": error_msg,
            "url": url,
        }
        return None

    def parse(self, response):
        """Parse the response and handle any HTTP errors."""
        self.logger.info(
            f"Received response from {response.url} with status {response.status}"
        )

        try:
            if response.status != 200:
                self._handle_error_response(response)
                return

            if self.check_only:
                self._handle_check_only(response)
                return

            property_item = self._extract_property_info(response)
            if not property_item:
                self._log_structured(
                    "error",
                    "Failed to extract property information",
                    {"url": response.url},
                )
                return

            current_time = datetime.now()
            property_overview = self._extract_property_overview(
                response, property_item.name, current_time, property_item.id
            )
            common_overview = self._extract_common_overview(
                response, current_time, property_item.id
            )

            user_property = {
                "line_user_id": self.line_user_id,
                "property_id": property_item.id,
                "last_aggregated_at": current_time,
                "next_aggregated_at": current_time + timedelta(days=3),
            }

            yield {
                "properties": property_item.model_dump(),
                "property_overviews": property_overview,
                "common_overviews": common_overview,
                "user_properties": user_property,
                "image_urls": property_item.image_urls,
            }

        except Exception as e:
            self._log_structured(
                "error", "Error in parse method", {"url": response.url}, error=e
            )
            self.results = {
                "status": "error",
                "error_type": e.__class__.__name__,
                "error_message": str(e),
                "url": response.url,
            }
            return

    def _handle_error_response(self, response):
        """Handle non-200 HTTP responses."""
        error_msg = ""
        if response.status == 404:
            error_msg = "Property not found (404). The URL may be incorrect or the property listing may have been removed."
        elif response.status == 403:
            error_msg = "Access forbidden (403). The site may be blocking scrapers."
        elif response.status == 500:
            error_msg = "Server error (500). The property site is experiencing issues."
        else:
            error_msg = f"HTTP error {response.status}"

        self.logger.error(f"HttpError on {response.url}")
        self.logger.error(f"HTTP Status Code: {response.status}")
        self.logger.error(error_msg)

        self.results = {
            "status": "not_found" if response.status == 404 else "error",
            "error_type": "HttpError",
            "error_message": error_msg,
            "url": response.url,
        }

    def _handle_check_only(self, response):
        """Handle check-only mode processing."""
        property_name = self._extract_property_name(response)
        if not property_name:
            error_msg = "Property name not found in response"
            self.logger.error(error_msg)
            self.results = {
                "status": "error",
                "error_type": "ParseError",
                "error_message": error_msg,
                "url": response.url,
            }
            return

        original_url = response.meta.get("original_url", "")
        is_redirected_to_library = self._is_redirected_to_library(
            response, original_url
        )

        self.results = {
            "status": "success",
            "property_name": property_name,
            "is_sold": is_redirected_to_library,
            "url": response.url,
        }

    def _log_http_error(
        self, level: str, context: Dict[str, Any], error: Exception
    ) -> None:
        """Log HTTP error messages in the expected format.

        Args:
            level: Log level
            context: Context dictionary
            error: Error object
        """
        self.logger.error(f"{error.__class__.__name__} on %s", context["url"])
        if "status_code" in context:
            self.logger.error("HTTP Status Code: %s", context["status_code"])
            if context["status_code"] == 403:
                self.logger.error(
                    "Access forbidden (403). The site may be blocking scrapers."
                )
            elif context["status_code"] == 500:
                self.logger.error(
                    "Server error (500). The property site is experiencing issues."
                )
            elif context["status_code"] == 404:
                self.logger.info(
                    "Property not found (404). The URL may be incorrect or the property listing may have been removed."
                )

    def _sanitize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize context data by converting MagicMock objects to strings.

        Args:
            context: Original context dictionary
        Returns:
            Sanitized context dictionary
        """
        sanitized_context = {}
        for key, value in context.items():
            if hasattr(value, "_mock_return_value"):  # Check if it's a MagicMock
                sanitized_context[key] = str(value)
            else:
                sanitized_context[key] = value
        return sanitized_context

    def _create_log_data(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
    ) -> Dict[str, Any]:
        """Create structured log data.

        Args:
            message: Log message
            context: Context dictionary
            error: Error object
        Returns:
            Structured log data dictionary
        """
        log_data = {
            "message": message,
            "spider": self.name,
            "timestamp": datetime.now().isoformat(),
        }

        if context:
            log_data["context"] = self._sanitize_context(context)

        if error:
            log_data["error"] = {
                "type": error.__class__.__name__,
                "message": str(error),
            }
            if hasattr(error, "__traceback__"):
                import traceback

                log_data["error"]["traceback"] = traceback.format_exc()

        return log_data

    def _log_structured(
        self,
        level: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
    ) -> None:
        """Log a structured message with context.

        Args:
            level: Log level (info, warning, error)
            message: Main log message
            context: Additional context as dictionary
            error: Exception object if logging an error
        """
        # First, log the message in the expected format for tests
        if context and "url" in context and level == "error":
            self._log_http_error(level, context, error)

        # Then create and log the structured message
        try:
            log_data = self._create_log_data(message, context, error)
            log_message = json.dumps(log_data)

            if level == "info":
                self.logger.info(log_message)
            elif level == "warning":
                self.logger.warning(log_message)
            elif level == "error":
                self.logger.error(log_message)
        except TypeError as e:
            # Fallback to simple logging if JSON serialization fails
            self.logger.error(f"Failed to serialize log data: {str(e)}")
            self.logger.error(message)

    def _extract_property_name(self, response: Response) -> Optional[str]:
        """Extract the property name from the response.

        Args:
            response: Scrapy response object
        Returns:
            The property name if found, None otherwise
        """
        # Try the standard property page format first
        property_name_xpath = f'normalize-space(//tr[th/div[contains(text(), "{ElementKeys.PROPERTY_NAME.value}")]]/td)'
        property_name = response.xpath(property_name_xpath).get()

        # If not found and it's a library page, try the library page format
        if not property_name and "/library/" in response.url:
            property_name = self._extract_property_name_from_library(response)

        return property_name

    def _extract_property_name_from_library(self, response: Response) -> Optional[str]:
        """Extract the property name from a library page.

        Args:
            response: Scrapy response object
        Returns:
            The property name if found, None otherwise
        """
        # Try to extract from the h1 title
        property_name_xpath = "normalize-space(//h1)"
        property_name = response.xpath(property_name_xpath).get()

        if property_name:
            return property_name

        # Try alternative xpath for library pages
        property_name_xpath = 'normalize-space(//*[@id="mainContents"]/div/h1)'
        property_name = response.xpath(property_name_xpath).get()

        if property_name:
            return property_name

        # Try to extract from the page title
        title_xpath = "normalize-space(//title)"
        title = response.xpath(title_xpath).get()

        if title:
            # SUUMO titles often have the format "PropertyName | SUUMO"
            parts = title.split("|")
            if len(parts) > 1:
                return parts[0].strip()

            # Or they might have the format "PropertyName - SUUMO"
            parts = title.split("-")
            if len(parts) > 1:
                return parts[0].strip()

            # If no separators, just return the title
            return title

        return None

    def _extract_large_prop_desc(self, response: Response) -> Optional[str]:
        """Extract the property description from the response.

        Args:
            response: Scrapy response object
        Returns:
            The property description if found, None otherwise
        """
        large_prop_desc_xpath = (
            'normalize-space(//*[@id="mainContents"]/div[2]/div/div[1]/h3)'
        )
        return response.xpath(large_prop_desc_xpath).get()

    def _extract_small_prop_desc(self, response: Response) -> Optional[str]:
        """Extract the property description from the response.

        Args:
            response: Scrapy response object
        Returns:
            The property description if found, None otherwise
        """
        # Try different selectors in order of specificity
        selectors = [
            "#wrapper > section:nth-child(2) > div:nth-child(6) > section.inner > p",
            "#mainContents > div:nth-child(2) > div > div:nth-child(1) > p",
        ]

        for selector in selectors:
            section = (
                response.css(selector)
                if selector.startswith("#")
                else response.xpath(selector)
            )

            if section:
                # Get the inner HTML content
                content = section.get()
                if content:
                    # Clean up the content while preserving <br> tags:
                    # 1. Replace multiple <br> tags with a single one
                    content = re.sub(r"<br\s*/?>\s*<br\s*/?>", "<br>", content)
                    # 2. Remove all HTML tags except <br>
                    content = re.sub(r"<(?!br\s*/?>)[^>]+>", "", content)
                    # 3. Clean up any remaining HTML attributes from br tags
                    content = re.sub(r"<br[^>]*>", "<br>", content)
                    # 4. Clean up whitespace
                    content = re.sub(r"\s+", " ", content).strip()
                    return content

        self._log_structured(
            "warning",
            "Failed to extract small property description",
            {"url": response.url, "tried_selectors": selectors},
        )
        return None

    def _extract_image_urls(self, response: Response) -> List[str]:
        """Extract property image URLs.

        Args:
            response: Scrapy response object
        Returns:
            List of image URLs
        """
        # Check if this is a library page (sold-out property)
        original_url = response.meta.get("original_url", "")
        is_redirected_to_library = self._is_redirected_to_library(
            response, original_url
        )

        if is_redirected_to_library:
            self._log_structured(
                "info",
                "Skipping image extraction for sold-out property",
                {"url": response.url, "original_url": original_url},
            )
            return []

        # Step 1: Define XPath patterns to find image URLs
        xpath_patterns = self._get_image_xpath_patterns()

        # Step 2: Extract all URLs using the patterns
        all_urls = self._extract_urls_from_patterns(response, xpath_patterns)

        # Step 3: Process and filter the URLs
        image_urls = self._process_image_urls(all_urls)

        # Step 4: Log results
        if image_urls:
            self._log_structured(
                "info",
                "Successfully extracted image URLs",
                {
                    "url": response.url,
                    "image_count": len(image_urls),
                    "patterns_used": xpath_patterns,
                },
            )
        else:
            self._log_structured(
                "warning",
                "No image URLs found for active property",
                {"url": response.url, "patterns_tried": xpath_patterns},
            )

        return image_urls

    def _get_image_xpath_patterns(self):
        """Get XPath patterns for image URLs."""
        return [
            # Get image URLs from img tags
            "//div[contains(@class, 'lazyloader')]//img/@src",
            # Fallback patterns
            "//*[@id='js-lightbox']//a[@class='carousel_item-object js-slideLazy js-lightboxItem']/@data-src",
            # Get resized image URLs from hidden input fields
            "//input[starts-with(@id, 'imgG')]/@value",
        ]

    def _extract_urls_from_patterns(
        self, response: Response, patterns: List[str]
    ) -> List[str]:
        """Extract URLs using the provided XPath patterns.

        Args:
            response: Scrapy response object
            patterns: List of XPath patterns

        Returns:
            List of extracted URLs
        """
        # Try each pattern in order until we find images
        for pattern in patterns:
            urls = response.xpath(pattern).getall()
            if urls:
                self._log_structured(
                    "info",
                    "Found images with pattern",
                    {"pattern": pattern, "url_count": len(urls)},
                )
                # Return immediately when we find images
                # Remove duplicates while preserving order
                return list(dict.fromkeys(urls))

        self._log_structured(
            "warning", "No images found with any pattern", {"patterns_tried": patterns}
        )
        return []

    def _process_hidden_input_url(self, image_url: str) -> Optional[str]:
        """Process URL from hidden input field.

        Args:
            image_url: URL to process

        Returns:
            Processed URL or None if processing fails
        """
        try:
            # Remove any Japanese text after comma in the value attribute
            if "," in image_url:
                image_url = image_url.split(",")[0]

            # If it's already a resizeImage URL, use it as is
            if "resizeImage?src=" in image_url:
                return image_url

            if "src=" not in image_url:
                return None

            src_param = image_url.split("src=")[1].split("&")[0]
            src_param = urllib.parse.unquote(src_param)

            # If it's already a full URL, use it as is
            if src_param.startswith(("http://", "https://")):
                return src_param

            # Otherwise, construct the resizeImage URL
            return f"https://img01.suumo.com/jj/resizeImage?src={src_param}"
        except Exception as e:
            self._log_structured(
                "error",
                "Error processing URL from hidden input",
                {"image_url": image_url},
                error=e,
            )
            return None

    def _process_lightbox_url(self, image_url: str) -> str:
        """Process URL from lightbox gallery.

        Args:
            image_url: URL to process

        Returns:
            Processed URL with proper domain
        """
        # Remove leading slash if present to avoid double slashes
        image_url = image_url.lstrip("/")
        return (
            image_url
            if image_url.startswith(("http://", "https://"))
            else f"https://suumo.jp/{image_url}"
        )

    def _should_skip_url(self, image_url: str) -> bool:
        """Check if URL should be skipped.

        Args:
            image_url: URL to check

        Returns:
            True if URL should be skipped, False otherwise
        """
        return "spacer.gif" in image_url

    def _process_image_urls(self, image_urls: List[str]) -> List[str]:
        """Process image URLs to ensure they are properly formatted.

        Args:
            image_urls: List of URLs to process

        Returns:
            List of processed URLs
        """
        processed_urls = []

        for image_url in image_urls:
            if self._should_skip_url(image_url):
                continue

            processed_url = None
            if "src=" in image_url:
                processed_url = self._process_hidden_input_url(image_url)
            elif image_url.startswith("/") or "suumo.jp" in image_url:
                processed_url = self._process_lightbox_url(image_url)

            if processed_url and processed_url not in processed_urls:
                processed_urls.append(processed_url)

        return processed_urls

    def _extract_property_overview(
        self,
        response: Response,
        property_name: str,
        current_time,
        property_id: ObjectId,
    ) -> PropertyOverview:
        """Extract property overview details.

        Args:
            response: Scrapy response object
            property_name: Name of the property
            current_time: Current timestamp
            property_id: ID of the property
        Returns:
            PropertyOverview object containing property overview details
        """
        # Refactored XPath to handle different layout types in a single query
        property_title = property_name + ElementKeys.APERTMENT_SUFFIX.value

        # First pattern: secTitleOuter/secTitleInner pattern
        # Second pattern: alternative pattern with mainContents
        xpath = f"""(
            //div[contains(@class, "secTitleOuter")]/h3[contains(@class, "secTitleInner") and contains(text(), "{property_title}")]/ancestor::div/following-sibling::table/tbody/tr
            |
            //*[@id="mainContents"]/div/div/div/div/h3[contains(text(), "{property_title}")]/parent::div/following-sibling::table/tbody/tr
        )"""

        items = response.xpath(xpath)

        overview_dict = {}
        for item in items:
            keys = [
                k.strip() for k in item.xpath("th/div/text()").getall() if k.strip()
            ]
            values = [v.strip() for v in item.xpath("td/text()").getall() if v.strip()]
            overview_dict.update(dict(zip(keys, values)))

        overview_dict = translate_keys(overview_dict, PROPERTY_OVERVIEW_TRANSLATION_MAP)
        overview_dict.update(
            {
                "created_at": current_time,
                "updated_at": current_time,
                "property_id": property_id,
            }
        )
        return PropertyOverview(**overview_dict)

    def _extract_common_overview(
        self, response: Response, current_time, property_id: ObjectId
    ) -> CommonOverview:
        """Extract common overview details.

        Args:
            response: Scrapy response object
            current_time: Current timestamp
            property_id: ID of the property
        Returns:
            CommonOverview object containing common overview details
        """
        # Refactored XPath to handle both layout types in a single query
        # This combines the two previous patterns:
        # 1. @class="secTitleOuterR"]/h3[@class="secTitleInnerR"
        # 2. @class="secTitleOuterK"]/h3[@class="secTitleInnerK"
        xpath = f"""//div[contains(@class, "secTitleOuter") and (
            ./h3[contains(@class, "secTitleInner") and contains(text(), "{ElementKeys.COMMON_OVERVIEW.value}")]
        )]/following-sibling::table/tbody/tr"""

        items = response.xpath(xpath)

        # Extract raw data from the page
        raw_data = {}
        location = None
        for item in items:
            keys = [
                k.strip() for k in item.xpath("th/div/text()").getall() if k.strip()
            ]
            values = [v.strip() for v in item.xpath("td/text()").getall() if v.strip()]

            for k, v in zip(keys, values):
                if k == ElementKeys.LOCATION.value:
                    location = v
                    raw_data[k] = v
                elif k == ElementKeys.TRAFFIC.value:
                    # For transportation, we need to get all values
                    all_values = item.xpath("td//text()").getall()
                    # Filter out empty strings and strip whitespace
                    transportation_values = [v.strip() for v in all_values if v.strip()]
                    # Clean up transportation values by removing unwanted elements
                    cleaned_values = []
                    for val in transportation_values:
                        if val not in ["[", "]", "乗り換え案内"] and val != location:
                            cleaned_values.append(val)
                    raw_data[k] = cleaned_values
                else:
                    raw_data[k] = v

        # Translate keys using the mapping
        translated_dict = translate_keys(raw_data, COMMON_OVERVIEW_TRANSLATION_MAP)

        # Initialize with default values for all required fields
        overview_dict = {
            "location": "情報なし",
            "transportation": ["情報なし"],
            "total_units": "情報なし",
            "structure_floors": "情報なし",
            "site_area": "情報なし",
            "site_ownership_type": "情報なし",
            "usage_area": "情報なし",
            "parking_lot": "情報なし",
        }

        # Update the default values with the translated data
        overview_dict.update(translated_dict)

        # Add metadata
        overview_dict.update(
            {
                "property_id": property_id,
                "created_at": current_time,
                "updated_at": current_time,
            }
        )

        return CommonOverview(**overview_dict)

    def _validate_property_name(self, property_name: Optional[str], url: str) -> None:
        """Validate that a property name was found.

        Args:
            property_name: The extracted property name or None
            url: The URL of the page
        """
        if not property_name:
            self.logger.error(f"Property name not found in the response. URL: {url}")
            self.logger.error(
                "This may indicate that the page doesn't contain property information "
                "or has a different structure."
            )

    def _is_redirected_to_library(self, response: Response, original_url: str) -> bool:
        """Check if the response URL is a redirect to a library page (sold-out property).

        Args:
            response: Scrapy response object
            original_url: The original URL requested

        Returns:
            True if redirected to a library page, False otherwise
        """
        # Check if the URL has changed and contains "/library/"
        if (
            original_url
            and response.url != original_url
            and "/library/" in response.url
        ):
            self.logger.info(
                f"Detected redirect to library page (likely sold-out property). "
                f"Original URL: {original_url}, Redirected URL: {response.url}"
            )
            return True
        return False

    def _create_default_property_overview(
        self, current_time, property_id: Optional[ObjectId]
    ) -> PropertyOverview:
        """Create a default PropertyOverview object for library pages (sold-out properties).

        Args:
            current_time: Current timestamp
            property_id: ID of the property or None

        Returns:
            Default PropertyOverview object
        """
        # Create a dictionary with default values for all required fields
        none_value = "情報なし (売却済み)"

        overview_dict = {
            "sales_schedule": none_value,
            "event_information": none_value,
            "number_of_units_for_sale": none_value,
            "highest_price_range": none_value,
            "price": none_value,
            "maintenance_fee": none_value,
            "repair_reserve_fund": none_value,
            "first_repair_reserve_fund": none_value,
            "other_expenses": none_value,
            "floor_plan": none_value,
            "area": none_value,
            "other_area": none_value,
            "delivery_time": none_value,
            "completion_time": none_value,
            "floor": none_value,
            "direction": none_value,
            "energy_consumption_performance": none_value,
            "insulation_performance": none_value,
            "estimated_utility_cost": none_value,
            "renovation": none_value,
            "other_restrictions": none_value,
            "other_overview_and_special_notes": none_value,
            "created_at": current_time,
            "updated_at": current_time,
            "property_id": property_id,
        }

        return PropertyOverview(**overview_dict)

    def _create_default_common_overview(
        self, current_time, property_id: Optional[ObjectId]
    ) -> CommonOverview:
        """Create a default CommonOverview object for library pages (sold-out properties).

        Args:
            current_time: Current timestamp
            property_id: ID of the property or None

        Returns:
            Default CommonOverview object
        """
        # Create a dictionary with default values for all required fields
        overview_dict = {
            "location": "情報なし (売却済み)",
            "transportation": ["情報なし (売却済み)"],
            "total_units": "情報なし (売却済み)",
            "structure_floors": "情報なし (売却済み)",
            "site_area": "情報なし (売却済み)",
            "site_ownership_type": "情報なし (売却済み)",
            "usage_area": "情報なし (売却済み)",
            "parking_lot": "情報なし (売却済み)",
            "created_at": current_time,
            "updated_at": current_time,
            "property_id": property_id,
        }

        return CommonOverview(**overview_dict)

    def _extract_property_info(self, response: Response) -> Optional[Property]:
        """Extract property information and create Property object.

        Args:
            response: Response object

        Returns:
            Property object or None if extraction fails
        """
        try:
            # Check if this is a library page
            original_url = response.meta.get("original_url", "")
            is_redirected_to_library = self._is_redirected_to_library(
                response, original_url
            )

            # Extract property name from title
            title = response.xpath("//title/text()").get()
            if not title:
                self._log_structured(
                    "error", "Failed to extract title", {"url": response.url}
                )
                return None

            # Extract property name from title (format: "【SUUMO】PropertyName 中古マンション物件情報")
            property_name = (
                title.split("【")[1].split("】")[1].split(" 中古マンション")[0].strip()
            )

            # Handle library page (sold-out property)
            if is_redirected_to_library:
                return Property(
                    name=f"{property_name or '物件名不明'} (売却済み)",
                    url=response.url,
                    large_property_description="この物件は現在販売されていません。",
                    small_property_description="この物件は売却済みです。最新の情報はSUUMOのライブラリページでご確認ください。",
                    is_active=False,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    image_urls=[],
                    price=None,
                    address=None,
                    size=None,
                )

            # Extract price from h1 tag
            price_text = response.xpath(
                "//h1[contains(@class, 'mainIndex') and (contains(@class, 'mainIndexK') or contains(@class, 'mainIndexR'))]/text()"
            ).get()
            if not price_text:
                self._log_structured(
                    "error",
                    "Failed to extract price from h1 tag",
                    {"url": response.url},
                )
                return None

            # Extract price value (format: "PropertyName 7880万円（1LDK）")
            price_match = re.search(r"(\d+)万円", price_text)
            if not price_match:
                self._log_structured(
                    "error",
                    "Failed to extract price value",
                    {"url": response.url, "price_text": price_text},
                )
                return None

            price = int(price_match.group(1))

            # Extract property address
            address = response.xpath(
                "//td[preceding-sibling::th/div[contains(text(), '所在地')]]/text()"
            ).get()
            if not address:
                self._log_structured(
                    "error", "Failed to extract property address", {"url": response.url}
                )
                return None

            # Extract property size
            size_text = response.xpath(
                "//td[preceding-sibling::th/div[contains(text(), '専有面積')]]/text()"
            ).get()
            if not size_text:
                self._log_structured(
                    "error", "Failed to extract property size", {"url": response.url}
                )
                return None

            # Convert size text to float (in square meters)
            size = float("".join(c for c in size_text if c.isdigit() or c == "."))

            # Extract descriptions
            large_desc = self._extract_large_prop_desc(response)
            small_desc = self._extract_small_prop_desc(response)

            # Extract image URLs
            image_urls = self._extract_image_urls(response)

            # Create and return Property object
            property_obj = Property(
                name=property_name,
                url=response.url,
                price=price,
                address=address.strip(),
                size=size,
                large_property_description=large_desc,
                small_property_description=small_desc,
                is_active=True,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                image_urls=image_urls,
            )

            return property_obj

        except Exception as e:
            self._log_structured(
                "error",
                "Error extracting property info",
                {"url": response.url},
                error=e,
            )
            return None
