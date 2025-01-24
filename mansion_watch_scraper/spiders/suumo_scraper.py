import scrapy
from scrapy.spidermiddlewares.httperror import HttpError
from twisted.internet.error import DNSLookupError, TCPTimedOutError, TimeoutError

from app.services.dates import get_current_time
from enums.html_element_keys import ElementKeys


class MansionWatchSpider(scrapy.Spider):
    name = "mansion_watch_scraper"
    allowed_domains = ["suumo.jp"]

    def __init__(self, url=None, *args, **kwargs):
        super(MansionWatchSpider, self).__init__(*args, **kwargs)
        if url is not None:
            self.start_urls = [url]
        else:
            raise ValueError("Argument 'url' is required")

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
        self.logger.info("Got successful response from {}".format(response.url))

        # Use this type of xpath to get the target element because the number of elements often changes.
        property_name_xpath = f'normalize-space(//tr[th/div[contains(text(), "{ElementKeys.PROPERTY_NAME.value}")]]/td)'
        property_name = response.xpath(property_name_xpath).get()
        property_dict = {
            "name": property_name,
            "url": response.url,
            "created_at": get_current_time(),
            "updated_at": get_current_time(),
        }

        # 物件概要
        # Use this type of xpath to get the target element because the number of elements often changes.
        property_overview_xpath = f'//div[@class="secTitleOuterR"]/h3[@class="secTitleInnerR" and contains(text(), "{property_name + ElementKeys.APERTMENT_SUFFIX.value}")]/ancestor::div[@class="secTitleOuterR"]/following-sibling::table/tbody/tr'
        property_overview = response.xpath(property_overview_xpath)

        property_overview_dict = {}
        for property_overview_item in property_overview:
            keys = property_overview_item.xpath("th/div/text()").getall()
            normalized_keys = [key.strip() for key in keys if key.strip()]

            values = property_overview_item.xpath("td/text()").getall()
            normalized_values = [value.strip() for value in values if value.strip()]

            for key, value in zip(normalized_keys, normalized_values):
                property_overview_dict[key] = value
        property_overview_dict["created_at"] = get_current_time()
        property_overview_dict["updated_at"] = get_current_time()

        # 共通概要
        # Use this type of xpath to get the target element because the number of elements often changes.
        common_overview_xpath = f'//div[@class="secTitleOuterR"]/h3[@class="secTitleInnerR" and contains(text(), "{ElementKeys.COMMON_OVERVIEW.value}")]//ancestor::div[@class="secTitleOuterR"]/following-sibling::table/tbody/tr'
        common_overview = response.xpath(common_overview_xpath)

        common_overview_dict = {}
        for common_overview_item in common_overview:
            keys = common_overview_item.xpath("th/div/text()").getall()
            normalized_keys = [key.strip() for key in keys if key.strip()]

            values = common_overview_item.xpath("td/text()").getall()
            normalized_values = [value.strip() for value in values if value.strip()]

            for key, value in zip(normalized_keys, normalized_values):
                if key == ElementKeys.TRAFFIC.value:
                    common_overview_dict[key] = normalized_values
                else:
                    common_overview_dict[key] = value
        common_overview_dict["created_at"] = get_current_time()
        common_overview_dict["updated_at"] = get_current_time()

        output = {
            "properties": property_dict,
            "property_overviews": property_overview_dict,
            "common_overviews": common_overview_dict,
        }
        print(output)

        yield output
