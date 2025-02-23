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
        elif failure.check(DNSLookupError):
            request = failure.request
            self.logger.error("DNSLookupError on %s", request.url)
        elif failure.check(TimeoutError, TCPTimedOutError):
            request = failure.request
            self.logger.error("TimeoutError on %s", request.url)

    def _extract_property_name(self, response: Response) -> Optional[str]:
        """Extract the property name from the response.

        Args:
            response: Scrapy response object
        Returns:
            The property name if found, None otherwise
        """
        property_name_xpath = f'normalize-space(//tr[th/div[contains(text(), "{ElementKeys.PROPERTY_NAME.value}")]]/td)'
        return response.xpath(property_name_xpath).get()

    def _extract_image_urls(self, response: Response) -> List[str]:
        """Extract property image URLs.

        Args:
            response: Scrapy response object
        Returns:
            List of image URLs
        """
        property_image_xpath = '//*[@id="js-lightbox"]/li/div/a/@data-src'
        urls = response.xpath(property_image_xpath).getall()
        return urls

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
        xpath = f'//div[@class="secTitleOuterR"]/h3[@class="secTitleInnerR" and contains(text(), "{property_name + ElementKeys.APERTMENT_SUFFIX.value}")]/ancestor::div[@class="secTitleOuterR"]/following-sibling::table/tbody/tr'
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
        xpath = f'//div[@class="secTitleOuterR"]/h3[@class="secTitleInnerR" and contains(text(), "{ElementKeys.COMMON_OVERVIEW.value}")]//ancestor::div[@class="secTitleOuterR"]/following-sibling::table/tbody/tr'
        items = response.xpath(xpath)

        overview_dict = {}
        for item in items:
            keys = [
                k.strip() for k in item.xpath("th/div/text()").getall() if k.strip()
            ]
            values = [v.strip() for v in item.xpath("td/text()").getall() if v.strip()]
            for k, v in zip(keys, values):
                if k == ElementKeys.TRAFFIC.value:
                    overview_dict[k] = values[1:]
                else:
                    overview_dict[k] = v

        overview_dict = translate_keys(overview_dict, COMMON_OVERVIEW_TRANSLATION_MAP)
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

        property_name = self._extract_property_name(response)
        if not property_name:
            self.logger.warning(
                f"Property name not found in the response. URL: {response.url}"
            )

        property_dict = {
            "name": property_name if property_name else "物件名不明",
            "url": response.url,
            "is_active": bool(property_name),
            "created_at": current_time,
            "updated_at": current_time,
            "image_urls": self._extract_image_urls(response),
        }
        property_obj = Property(**property_dict)

        # Create base dictionaries without property_id
        user_property_dict = {
            "line_user_id": self.line_user_id,
            "last_aggregated_at": current_time,
            "next_aggregated_at": current_time + timedelta(days=3),
        }

        # Extract overviews without property_id
        property_overview = self._extract_property_overview(
            response, property_name, current_time, None
        )
        common_overview = self._extract_common_overview(response, current_time, None)

        yield {
            "properties": property_obj,
            "user_properties": user_property_dict,  # Pass dict instead of model
            "property_overviews": property_overview,
            "common_overviews": common_overview,
        }
