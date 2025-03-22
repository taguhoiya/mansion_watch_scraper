# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

import random
import time
import uuid

from scrapy import signals
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.utils.response import response_status_message

# useful for handling different item types with a single interface
# from itemadapter import ItemAdapter, is_item


class MansionWatchScraperSpiderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(self, response, result, spider):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, or item objects.
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Request or item objects.
        pass

    def process_start_requests(self, start_requests, spider):
        # Called with the start requests of the spider, and works
        # similarly to the process_spider_output() method, except
        # that it doesn't have a response associated.

        # Must return only requests (not items).
        for r in start_requests:
            yield r

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class MansionWatchScraperDownloaderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the downloader middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        # Called for each request that goes through the downloader
        # middleware.

        # Must either:
        # - return None: continue processing this request
        # - or return a Response object
        # - or return a Request object
        # - or raise IgnoreRequest: process_exception() methods of
        #   installed downloader middleware will be called
        return None

    def process_response(self, request, response, spider):
        # Called with the response returned from the downloader.

        # Must either;
        # - return a Response object
        # - return a Request object
        # - or raise IgnoreRequest
        return response

    def process_exception(self, request, exception, spider):
        # Called when a download handler or a process_request()
        # (from other downloader middleware) raises an exception.

        # Must either:
        # - return None: continue processing this exception
        # - return a Response object: stops process_exception() chain
        # - return a Request object: stops process_exception() chain
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class AntiScrapingMiddleware:
    """Middleware to handle anti-scraping measures."""

    def __init__(self):
        """Initialize the middleware."""
        self.user_agents = [
            # Chrome
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            # Firefox
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:123.0) Gecko/20100101 Firefox/123.0",
            # Safari
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            # Edge
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
        ]

        # Common headers for all requests
        self.common_headers = {
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Ch-Ua": '"Not A(Brand";v="99", "Chromium";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "DNT": "1",
            "Sec-GPC": "1",
        }

        # Headers specific to regular page requests
        self.page_specific_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
        }

        # Headers specific to image requests
        self.image_specific_headers = {
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Sec-Fetch-Dest": "image",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "same-origin",
        }

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls()
        return middleware

    def process_request(self, request, spider):
        """Process the request by adding anti-scraping measures."""
        # Set a random User-Agent
        request.headers["User-Agent"] = random.choice(self.user_agents)

        # Add common headers
        request.headers.update(self.common_headers)

        # Add request-specific headers
        if "resizeImage" in request.url:
            request.headers.update(self.image_specific_headers)
            # Add cookies for image requests
            request.cookies.update(
                {
                    "nowtime": str(int(time.time())),  # Current timestamp
                    "uid": f"uid_{uuid.uuid4().hex[:16]}",  # Random user ID
                    "session": f"session_{uuid.uuid4().hex}",  # Random session ID
                }
            )
            # Set referer based on the request's domain
            parsed_url = request.url.split("/")
            if len(parsed_url) >= 3:
                base_url = f"{parsed_url[0]}//{parsed_url[2]}"
                request.headers["Referer"] = base_url
                request.headers["Origin"] = base_url
        else:
            request.headers.update(self.page_specific_headers)

        # Add random delay between requests (2-6 seconds)
        time.sleep(random.uniform(2.0, 6.0))
        return None

    def process_response(self, request, response, spider):
        # If we get a 503, add a longer delay before retrying
        if response.status == 503:
            time.sleep(random.uniform(10.0, 20.0))
        return response


class CustomRetryMiddleware(RetryMiddleware):
    """Custom retry middleware with enhanced retry logic."""

    def process_response(self, request, response, spider):
        if request.meta.get("dont_retry", False):
            return response

        # Check if the response is an image with zero size or error content
        if request.url.endswith((".jpg", ".jpeg", ".png")):
            content_length = len(response.body)
            content_type = response.headers.get("Content-Type", b"").decode(
                "utf-8", "ignore"
            )

            # Retry if image is too small or has wrong content type
            if content_length < 1000 or "text/html" in content_type:
                reason = f"Invalid image response (size: {content_length}, type: {content_type})"
                return self._retry(request, reason, spider) or response

        # Handle other response codes
        if response.status in self.retry_http_codes:
            reason = response_status_message(response.status)
            return self._retry(request, reason, spider) or response

        return response
