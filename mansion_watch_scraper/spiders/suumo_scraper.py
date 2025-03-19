import re
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Optional

import scrapy
from bson.objectid import ObjectId
from scrapy.http import Response
from scrapy.spidermiddlewares.httperror import HttpError
from twisted.internet.error import DNSLookupError, TCPTimedOutError, TimeoutError

from app.models.common_overview import COMMON_OVERVIEW_TRANSLATION_MAP, CommonOverview
from app.models.property import Property
from app.models.property_overview import (
    PROPERTY_OVERVIEW_TRANSLATION_MAP,
    PropertyOverview,
)
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
            ValueError: If url or line_user_id is missing or invalid
        """
        super(MansionWatchSpider, self).__init__(*args, **kwargs)
        if url is not None:
            self.start_urls = [url]
        if line_user_id is not None:
            if not line_user_id.startswith("U"):
                raise ValueError("line_user_id must start with U")
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
        image_urls = self._process_image_urls(all_urls)

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
                self.logger.info(f"Found {len(urls)} images with pattern {pattern}")
                # Return immediately when we find images
                # Remove duplicates while preserving order
                return list(dict.fromkeys(urls))

        self.logger.warning("No images found with any pattern")
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
            self.logger.error(f"Error processing URL from hidden input: {e}")
            self.logger.error(f"Problem URL: {image_url}")
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

    def parse(self, response: Response):
        """Parse the response from SUUMO.

        Args:
            response: Response object

        Yields:
            Item with property information
        """
        try:
            # Extract property information
            property_info = self._extract_property_info(response)
            if not property_info:
                self.logger.error("Failed to extract property information")
                return None

            # Extract image URLs
            image_urls = self._extract_image_urls(response)
            if not image_urls:
                self.logger.warning("No image URLs found")
                return None

            # Create property item with image URLs
            property_item = Property(
                **property_info,
                image_urls=image_urls,  # Include image URLs in the property item
                line_user_id=self.line_user_id,
                url=response.url,
                last_aggregated_at=datetime.now(),
                next_aggregated_at=datetime.now() + timedelta(days=3),
                is_active=True,  # Add is_active field
            )

            # Create item dictionary with both property data and image URLs
            item = {
                "properties": property_item,
                "user_properties": {
                    "line_user_id": self.line_user_id,
                    "last_aggregated_at": datetime.now(),
                    "next_aggregated_at": datetime.now() + timedelta(days=3),
                },
                "image_urls": image_urls,  # Add image URLs for the image pipeline
            }

            yield item

        except Exception as e:
            self.logger.error(f"Error in parse: {e}")
            return None

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

    def _extract_property_info(self, response):
        """Extract property information from the response.

        Args:
            response: Response object

        Returns:
            Dictionary containing property information
        """
        try:
            # Extract property name from title
            title = response.xpath("//title/text()").get()
            if not title:
                self.logger.error("Failed to extract title")
                return None

            # Extract property name from title (format: "【SUUMO】PropertyName 中古マンション物件情報")
            property_name = (
                title.split("【")[1].split("】")[1].split(" 中古マンション")[0]
            )
            if not property_name:
                self.logger.error("Failed to extract property name from title")
                return None

            # Extract property price from h1 tag
            price_text = response.xpath(
                "//h1[contains(@class, 'mainIndex') and (contains(@class, 'mainIndexK') or contains(@class, 'mainIndexR'))]/text()"
            ).get()
            if not price_text:
                self.logger.error("Failed to extract price from h1 tag")
                return None

            # Extract price value (format: "PropertyName 7880万円（1LDK）")
            price_match = re.search(r"(\d+)万円", price_text)
            if not price_match:
                self.logger.error("Failed to extract price value")
                return None

            price = int(price_match.group(1))

            # Extract property address from table data
            address = response.xpath(
                "//td[preceding-sibling::th/div[contains(text(), '所在地')]]/text()"
            ).get()
            if not address:
                self.logger.error("Failed to extract property address")
                return None

            # Extract property size from table data
            size_text = response.xpath(
                "//td[preceding-sibling::th/div[contains(text(), '専有面積')]]/text()"
            ).get()
            if not size_text:
                self.logger.error("Failed to extract property size")
                return None

            # Convert size text to float (in square meters)
            # Remove non-numeric characters except decimal point and convert to float
            size = float("".join(c for c in size_text if c.isdigit() or c == "."))

            # Create property info dictionary
            property_info = {
                "name": property_name.strip(),
                "price": price,
                "address": address.strip(),
                "size": size,
                "status": "active",  # Default status
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }

            self.logger.info(f"Successfully extracted property info: {property_info}")
            return property_info

        except Exception as e:
            self.logger.error(f"Error extracting property information: {e}")
            return None
