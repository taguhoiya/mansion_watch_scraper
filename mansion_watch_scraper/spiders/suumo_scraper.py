import html
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
                meta={
                    "original_url": url
                },  # Store the original URL for redirect detection
            )

    def errback_httpbin(self, failure):
        """Handle various network and HTTP errors.

        Args:
            failure: The failure object containing error details
        """
        self.logger.error(repr(failure))

        if failure.check(HttpError):
            response = failure.value.response

            # For 404 errors, log as INFO instead of ERROR since it's an expected scenario
            if response.status == 404:
                self.logger.info("HttpError on %s", response.url)
                self.logger.info("HTTP Status Code: %s", response.status)
                self.logger.info(
                    "Property not found (404). The URL may be incorrect or the property listing may have been removed."
                )
            else:
                # For other HTTP errors, continue to log as ERROR
                self.logger.error("HttpError on %s", response.url)
                self.logger.error("HTTP Status Code: %s", response.status)

                if response.status == 403:
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
        # Check if this is a library page (sold-out property)
        original_url = response.meta.get("original_url", "")
        is_redirected_to_library = self._is_redirected_to_library(
            response, original_url
        )

        if is_redirected_to_library:
            self.logger.info(
                "Skipping image extraction for sold-out property (library page)"
            )
            # Return an empty list for sold-out properties
            return []

        # Step 1: Define XPath patterns to find image URLs
        xpath_patterns = self._get_image_xpath_patterns()

        # Step 2: Extract all URLs using the patterns
        all_urls = self._extract_urls_from_patterns(response, xpath_patterns)

        # Step 3: Process and filter the URLs
        image_urls = self._process_image_urls(response, all_urls)

        # Step 4: Log results
        if image_urls:
            self.logger.info(f"Total unique image URLs found: {len(image_urls)}")
        else:
            self.logger.warning(
                "No image URLs found for active property - this may indicate an issue with the page structure"
            )

        return image_urls

    def _get_image_xpath_patterns(self):
        """Get XPath patterns for image URLs."""
        return [
            # Get image URLs from lightbox gallery
            "//*[@id='js-lightbox']//a[@class='carousel_item-object js-slideLazy js-lightboxItem']/@data-src",
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
        processed_urls = set()
        for url in urls:
            # Split the value by comma to separate URL from description
            parts = url.split(",")
            if not parts:
                continue

            # Get the URL part and remove any HTML entities
            image_url = parts[0].strip()
            image_url = html.unescape(image_url)

            # Make URL absolute if it's relative
            if image_url.startswith("/"):
                image_url = f"https://img01.suumo.com{image_url}"

            self.logger.debug(f"Found image URL: {image_url}")
            processed_urls.add(image_url)

        self.logger.info(f"Total unique image URLs found: {len(processed_urls)}")
        return list(processed_urls)

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

        # Check if the response URL is a redirect to a library page (sold-out property)
        original_url = response.meta.get("original_url", "")
        is_redirected_to_library = self._is_redirected_to_library(
            response, original_url
        )

        # Step 1: Extract property name and validate
        property_name = self._extract_property_name(response)

        # For library pages, we don't need to log an error if property name is not found
        if not is_redirected_to_library:
            self._validate_property_name(property_name, response.url)

        # Step 2: Extract property data
        property_obj = self._create_property_object(
            response, property_name, current_time, is_redirected_to_library
        )

        # Step 3: Create user property data
        user_property_dict = self._create_user_property_dict(current_time)

        # Step 4: Extract overview data or create default objects for library pages
        if is_redirected_to_library:
            # For library pages (sold-out properties), create default overview objects
            # to avoid validation errors
            self.logger.info(
                "Creating default overview objects for library page (sold-out property)"
            )
            property_overview = self._create_default_property_overview(
                current_time, None
            )
            common_overview = self._create_default_common_overview(current_time, None)
        else:
            # For normal property pages, extract overview data as usual
            property_overview = self._extract_property_overview(
                response, property_name, current_time, None
            )
            common_overview = self._extract_common_overview(
                response, current_time, None
            )

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
        overview_dict = {
            "sales_schedule": "情報なし (売却済み)",
            "event_information": "情報なし (売却済み)",
            "number_of_units_for_sale": "情報なし (売却済み)",
            "highest_price_range": "情報なし (売却済み)",
            "price": "情報なし (売却済み)",
            "maintenance_fee": "情報なし (売却済み)",
            "repair_reserve_fund": "情報なし (売却済み)",
            "first_repair_reserve_fund": "情報なし (売却済み)",
            "other_expenses": "情報なし (売却済み)",
            "floor_plan": "情報なし (売却済み)",
            "area": "情報なし (売却済み)",
            "other_area": "情報なし (売却済み)",
            "delivery_time": "情報なし (売却済み)",
            "completion_time": "情報なし (売却済み)",
            "floor": "情報なし (売却済み)",
            "direction": "情報なし (売却済み)",
            "energy_consumption_performance": "情報なし (売却済み)",
            "insulation_performance": "情報なし (売却済み)",
            "estimated_utility_cost": "情報なし (売却済み)",
            "renovation": "情報なし (売却済み)",
            "other_restrictions": "情報なし (売却済み)",
            "other_overview_and_special_notes": "情報なし (売却済み)",
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

    def _create_property_object(
        self,
        response: Response,
        property_name: Optional[str],
        current_time,
        is_redirected_to_library: bool = False,
    ) -> Property:
        """Create a Property object from the extracted data.

        Args:
            response: Scrapy response object
            property_name: The extracted property name or None
            current_time: Current timestamp
            is_redirected_to_library: Whether the request was redirected to a library page

        Returns:
            Property object
        """
        # If redirected to library page, mark as inactive regardless of property name
        is_active = not is_redirected_to_library and bool(property_name)

        # For library pages, add a note about the property being sold out
        if is_redirected_to_library:
            # If we have a property name from the library page, use it
            if property_name:
                display_name = property_name
            else:
                # Try to extract property name from the URL or use a default
                url_parts = response.url.split("/")
                if len(url_parts) > 4:
                    # Extract potential property name from URL
                    display_name = url_parts[4].replace("_", " ").title()
                else:
                    display_name = "物件名不明"

            # Add a note about the property being sold out
            property_name = f"{display_name} (売却済み)"
            large_desc = "この物件は現在販売されていません。"
            small_desc = "この物件は売却済みです。最新の情報はSUUMOのライブラリページでご確認ください。"
            # Empty image_urls for sold-out properties
            image_urls = []
        else:
            large_desc = self._extract_large_prop_desc(response)
            small_desc = self._extract_small_prop_desc(response)
            image_urls = self._extract_image_urls(response)

        property_dict = {
            "name": property_name if property_name else "物件名不明",
            "url": response.url,
            "large_property_description": large_desc,
            "small_property_description": small_desc,
            "is_active": is_active,
            "created_at": current_time,
            "updated_at": current_time,
            "image_urls": image_urls,
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
