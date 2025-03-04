from datetime import timedelta
from typing import List, Optional

import scrapy
from bson.objectid import ObjectId  # Changed from PyObjectId to ObjectId
from scrapy.http import Response
from scrapy.spidermiddlewares.httperror import HttpError
from twisted.internet.error import DNSLookupError, TCPTimedOutError, TimeoutError

from app.models.common_overview import COMMON_OVERVIEW_TRANSLATION_MAP, CommonOverview
from app.models.property import Property
from app.models.property_overview import (
    PROPERTY_OVERVIEW_TRANSLATION_MAP,
    PropertyOverview,
)
from app.services.dates import get_current_time
from app.services.utils import translate_keys
from enums.html_element_keys import ElementKeys


class MansionWatchSpider(scrapy.Spider):
    """Spider for scraping mansion property details from SUUMO website."""

    name = "mansion_watch_scraper"
    allowed_domains = ["suumo.jp"]

    def __init__(
        self,
        url: Optional[str] = None,
        line_user_id: Optional[str] = None,
        *args,
        **kwargs,
    ):
        """Initialize the spider with URL and user ID.

        Args:
            url: The URL to scrape
            line_user_id: The Line user ID
        Raises:
            ValueError: If url or line_user_id is missing
        """
        super(MansionWatchSpider, self).__init__(*args, **kwargs)
        if url is not None:
            self.start_urls = [url]
        if line_user_id is not None:
            self.line_user_id = line_user_id
        if not line_user_id or not url:
            raise ValueError(
                f"Both url and line_user_id are required. url: {url}, line_user_id: {line_user_id}"
            )

    def start_requests(self):
        """Start the scraping requests with error handling."""
        for url in self.start_urls:
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                errback=self.errback_httpbin,
                dont_filter=True,
            )

    def errback_httpbin(self, failure):
        """Handle various network and HTTP errors.

        Args:
            failure: The failure object containing error details
        """
        self.logger.error(repr(failure))

        if failure.check(HttpError):
            response = failure.value.response
            self.logger.error("HttpError on %s", response.url)
            self.logger.error("HTTP Status Code: %s", response.status)

            # For 404 errors, provide a more specific message
            if response.status == 404:
                self.logger.error(
                    "Property not found (404). The URL may be incorrect or the property listing may have been removed."
                )
            elif response.status == 403:
                self.logger.error(
                    "Access forbidden (403). The site may be blocking scrapers."
                )
            elif response.status == 500:
                self.logger.error(
                    "Server error (500). The property site is experiencing issues."
                )

        elif failure.check(DNSLookupError):
            request = failure.request
            self.logger.error("DNSLookupError on %s", request.url)
            self.logger.error(
                "Could not resolve domain name. Check internet connection or if the domain exists."
            )

        elif failure.check(TimeoutError, TCPTimedOutError):
            request = failure.request
            self.logger.error("TimeoutError on %s", request.url)
            self.logger.error(
                "Request timed out. The server may be slow or unresponsive."
            )

        else:
            # Handle other types of errors
            request = failure.request
            self.logger.error("Unknown error on %s: %s", request.url, str(failure))

    def _extract_property_name(self, response: Response) -> Optional[str]:
        """Extract the property name from the response.

        Args:
            response: Scrapy response object
        Returns:
            The property name if found, None otherwise
        """
        property_name_xpath = f'normalize-space(//tr[th/div[contains(text(), "{ElementKeys.PROPERTY_NAME.value}")]]/td)'
        return response.xpath(property_name_xpath).get()

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
        small_prop_desc_xpath = '//*[@id="mainContents"]/div[2]/div/div[1]/p'
        desc = response.xpath(small_prop_desc_xpath).get()
        if desc:
            # Replace closing p tag first to avoid issues
            desc = desc.replace("</p>", "")
            # Remove opening p tag with any attributes
            desc = desc.replace(desc[desc.find("<p") : desc.find(">") + 1], "")
        return desc

    def _extract_image_urls(self, response: Response) -> List[str]:
        """Extract property image URLs.

        Args:
            response: Scrapy response object
        Returns:
            List of image URLs
        """
        # Step 1: Define XPath patterns to find image URLs
        xpath_patterns = self._get_image_xpath_patterns()

        # Step 2: Extract all URLs using the patterns
        all_urls = self._extract_urls_from_patterns(response, xpath_patterns)

        # Step 3: Process and filter the URLs
        image_urls = self._process_image_urls(response, all_urls)

        # Step 4: Log results
        self._log_image_extraction_results(image_urls)

        return image_urls

    def _get_image_xpath_patterns(self) -> List[str]:
        """Get a list of XPath patterns to extract image URLs.

        Returns:
            List of XPath patterns
        """
        return [
            # Lazy-loaded property images (most common on SUUMO)
            '//img[@class="js-scrollLazy-image"]/@rel',
            # Main property images
            '//div[contains(@class, "mainphoto")]//img/@src',
            '//div[contains(@class, "mainphoto")]//img/@data-src',
            # Thumbnail property images
            '//div[contains(@class, "thumbnail")]//img/@src',
            '//div[contains(@class, "thumbnail")]//img/@data-src',
            # Property image gallery
            '//div[contains(@class, "photo")]//img/@src',
            '//div[contains(@class, "photo")]//img/@data-src',
            # Lightbox/gallery images
            '//*[@id="js-lightbox"]//img/@src',
            '//*[@id="js-lightbox"]/li/div/a/@data-src',
            # Fallback for any remaining images (will be filtered by _process_image_urls)
            "//img/@src",
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
        all_urls = []
        for pattern in patterns:
            urls = response.xpath(pattern).getall()
            if urls:
                all_urls.extend(urls)

        # Remove duplicates while preserving order
        return list(dict.fromkeys(all_urls))

    def _process_image_urls(self, response: Response, urls: List[str]) -> List[str]:
        """Process and filter image URLs.

        Args:
            response: Scrapy response object
            urls: List of URLs to process

        Returns:
            List of processed image URLs
        """
        processed_urls = []

        # Regular expression to match property images
        import re

        # Match patterns like bukken/030/N010000/img/419/76856419/76856419_0019.jpg
        property_image_pattern = re.compile(r"bukken.*\d+\.jpg", re.IGNORECASE)

        for url in urls:
            # Skip empty URLs
            if not url or url.strip() == "":
                continue

            # Skip if not a property image
            if not property_image_pattern.search(url):
                continue

            # Handle relative URLs
            if url.startswith("/"):
                url = response.urljoin(url)
            # Handle URLs with scheme
            elif not (url.startswith("http://") or url.startswith("https://")):
                # Try to fix URLs without scheme
                if url.startswith("//"):
                    url = "https:" + url
                else:
                    self.logger.warning(f"Skipping URL without proper scheme: {url}")
                    continue

            # Skip URLs that are not from suumo.jp or related domains
            if not ("suumo" in url or "recruit" in url):
                self.logger.warning(f"Skipping non-SUUMO URL: {url}")
                continue

            # Skip duplicate URLs
            if url in processed_urls:
                continue

            processed_urls.append(url)

        return processed_urls

    def _log_image_extraction_results(self, image_urls: List[str]) -> None:
        """Log the results of image extraction.

        Args:
            image_urls: List of extracted image URLs
        """
        self.logger.info(f"Total unique image URLs found: {len(image_urls)}")

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

    def parse(self, response: Response):
        """Parse the scraped data from the response.

        Args:
            response: Scrapy response object
        Yields:
            Dictionary containing all extracted property information
        """
        self.logger.info("Successful response from %s", response.url)
        current_time = get_current_time()

        # Step 1: Extract property name and validate
        property_name = self._extract_property_name(response)
        self._validate_property_name(property_name, response.url)

        # Step 2: Extract property data
        property_obj = self._create_property_object(
            response, property_name, current_time
        )

        # Step 3: Create user property data
        user_property_dict = self._create_user_property_dict(current_time)

        # Step 4: Extract overview data
        property_overview = self._extract_property_overview(
            response, property_name, current_time, None
        )
        common_overview = self._extract_common_overview(response, current_time, None)

        # Step 5: Yield the complete item
        yield {
            "properties": property_obj,
            "user_properties": user_property_dict,
            "property_overviews": property_overview,
            "common_overviews": common_overview,
        }

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

    def _create_property_object(
        self, response: Response, property_name: Optional[str], current_time
    ) -> Property:
        """Create a Property object from the extracted data.

        Args:
            response: Scrapy response object
            property_name: The extracted property name or None
            current_time: Current timestamp

        Returns:
            Property object
        """
        property_dict = {
            "name": property_name if property_name else "物件名不明",
            "url": response.url,
            "large_property_description": self._extract_large_prop_desc(response),
            "small_property_description": self._extract_small_prop_desc(response),
            "is_active": bool(property_name),
            "created_at": current_time,
            "updated_at": current_time,
            "image_urls": self._extract_image_urls(response),
        }
        return Property(**property_dict)

    def _create_user_property_dict(self, current_time) -> dict:
        """Create a dictionary with user property data.

        Args:
            current_time: Current timestamp

        Returns:
            Dictionary with user property data
        """
        return {
            "line_user_id": self.line_user_id,
            "last_aggregated_at": current_time,
            "next_aggregated_at": current_time + timedelta(days=3),
        }
