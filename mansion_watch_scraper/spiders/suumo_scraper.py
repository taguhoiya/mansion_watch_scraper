from datetime import timedelta

import scrapy
from scrapy.spidermiddlewares.httperror import HttpError
from twisted.internet.error import DNSLookupError, TCPTimedOutError, TimeoutError

from app.models.common_overview import COMMON_OVERVIEW_TRANSLATION_MAP, CommonOverview
from app.models.property import Property
from app.models.property_overview import (
    PROPERTY_OVERVIEW_TRANSLATION_MAP,
    PropertyOverview,
)
from app.models.user_property import UserProperty
from app.services.dates import get_current_time
from app.services.utils import translate_keys
from enums.html_element_keys import ElementKeys


class MansionWatchSpider(scrapy.Spider):
    name = "mansion_watch_scraper"
    allowed_domains = ["suumo.jp"]

    def __init__(self, url=None, line_user_id=None, *args, **kwargs):
        super(MansionWatchSpider, self).__init__(*args, **kwargs)
        if url is not None:
            self.start_urls = [url]
        if line_user_id is not None:
            self.line_user_id = line_user_id
        if not line_user_id or not url:
            raise ValueError(
                f"Both url and line_user_id are required. url: {url}, line_user_id: {line_user_id}"
            )

    # Ref: https://docs.scrapy.org/en/latest/topics/request-response.html#topics-request-response-ref-errbacks
    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                errback=self.errback_httpbin,
            )

    def errback_httpbin(self, failure):
        # log all failures
        self.logger.error(repr(failure))

        if failure.check(HttpError):
            # these exceptions come from HttpError spider middleware
            # you can get the non-200 response
            response = failure.value.response
            self.logger.error("HttpError on %s", response.url)

        elif failure.check(DNSLookupError):
            # this is the original request
            request = failure.request
            self.logger.error("DNSLookupError on %s", request.url)

        elif failure.check(TimeoutError, TCPTimedOutError):
            request = failure.request
            self.logger.error("TimeoutError on %s", request.url)

    def parse(self, response):
        self.logger.info("Successful response from %s", response.url)
        current_time = get_current_time()

        # Extract a property name to check if the property is available to scrape
        property_name_xpath = f'normalize-space(//tr[th/div[contains(text(), "{ElementKeys.PROPERTY_NAME.value}")]]/td)'
        property_name = response.xpath(property_name_xpath).get()

        property_dict: dict[str, Property] = {}
        if not property_name:
            self.logger.warning(
                f"Property name not found in the response. URL: {response.url}"
            )

        property_dict = {
            "name": property_name if property_name else "物件名不明",
            "url": response.url,
            "is_active": True if property_name else False,
            "created_at": current_time,
            "updated_at": current_time,
        }
        user_property_dict: dict[str, UserProperty] = {
            "line_user_id": self.line_user_id,
            "last_aggregated_at": current_time,  # start update_at
            "next_aggregated_at": current_time + timedelta(days=3),  # 3 days later
            "first_succeeded_at": current_time,  # created_at
            "last_succeeded_at": current_time,  # end update_at
        }

        # Extract property images
        property_image_xpath = '//*[@id="js-lightbox"]/li/div/a/@data-src'
        image_urls = response.xpath(property_image_xpath).getall()
        property_dict["image_urls"] = image_urls

        # Extract property overview details
        property_overview_xpath = f'//div[@class="secTitleOuterR"]/h3[@class="secTitleInnerR" and contains(text(), "{property_name + ElementKeys.APERTMENT_SUFFIX.value}")]/ancestor::div[@class="secTitleOuterR"]/following-sibling::table/tbody/tr'
        property_overview_items = response.xpath(property_overview_xpath)
        property_overview_dict: dict[str, PropertyOverview] = {}
        for item in property_overview_items:
            keys = [
                k.strip() for k in item.xpath("th/div/text()").getall() if k.strip()
            ]
            values = [v.strip() for v in item.xpath("td/text()").getall() if v.strip()]
            property_overview_dict.update(dict(zip(keys, values)))

        property_overview_dict = translate_keys(
            property_overview_dict, PROPERTY_OVERVIEW_TRANSLATION_MAP
        )
        property_overview_dict.update(
            {"created_at": current_time, "updated_at": current_time}
        )

        # Extract common overview details
        common_overview_xpath = f'//div[@class="secTitleOuterR"]/h3[@class="secTitleInnerR" and contains(text(), "{ElementKeys.COMMON_OVERVIEW.value}")]//ancestor::div[@class="secTitleOuterR"]/following-sibling::table/tbody/tr'
        common_overview_items = response.xpath(common_overview_xpath)
        common_overview_dict: dict[str, CommonOverview] = {}
        for item in common_overview_items:
            keys = [
                k.strip() for k in item.xpath("th/div/text()").getall() if k.strip()
            ]
            values = [v.strip() for v in item.xpath("td/text()").getall() if v.strip()]
            for k, v in zip(keys, values):
                # Extract traffic details separately since it has multiple values and is saved as a list
                if k == ElementKeys.TRAFFIC.value:
                    # Exclude the first value since it is the value of the key (location: 所在地)
                    common_overview_dict[k] = values[1:]
                else:
                    common_overview_dict[k] = v

        common_overview_dict = translate_keys(
            common_overview_dict, COMMON_OVERVIEW_TRANSLATION_MAP
        )
        common_overview_dict.update(
            {"created_at": current_time, "updated_at": current_time}
        )

        output = {
            "properties": property_dict,
            "user_properties": user_property_dict,
            "property_overviews": property_overview_dict,
            "common_overviews": common_overview_dict,
        }
        yield output
