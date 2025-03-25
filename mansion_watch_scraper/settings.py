import os

# Scrapy settings for mansion_watch_scraper project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "mansion_watch_scraper"

SPIDER_MODULES = ["mansion_watch_scraper.spiders"]
NEWSPIDER_MODULE = "mansion_watch_scraper.spiders"


# Crawl responsibly by identifying yourself (and your website) on the user-agent
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Obey robots.txt rules
ROBOTSTXT_OBEY = False

# Configure maximum concurrent requests performed by Scrapy (default: 16)
CONCURRENT_REQUESTS = 1

# Configure a delay for requests for the same website (default: 0)
DOWNLOAD_DELAY = 0  # No delay for single URL checks
RANDOMIZE_DOWNLOAD_DELAY = False

# Enable cookies and cookie debugging
COOKIES_ENABLED = False
COOKIES_DEBUG = False  # Disable cookie debugging

# Disable Telnet Console (enabled by default)
TELNETCONSOLE_ENABLED = False

# Override the default request headers:
# DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
# }

# Configure spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
SPIDER_MIDDLEWARES = {
    "scrapy.spidermiddlewares.httperror.HttpErrorMiddleware": 543,
}

# Configure retry settings
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]  # Don't retry 404s

# Configure download settings
DOWNLOAD_TIMEOUT = 120  # Increased from 30 to 120 seconds

# Configure image pipeline settings
IMAGES_STORE_FORMAT = "JPEG"
IMAGES_MIN_HEIGHT = 50
IMAGES_MIN_WIDTH = 50

# Allow image domains for downloading
IMAGES_DOMAINS = [
    "img01.suumo.com",
    "img02.suumo.com",
    "img03.suumo.com",
    "maintenance.suumo.jp",
]

# Enable caching
HTTPCACHE_ENABLED = False
# HTTPCACHE_EXPIRATION_SECS = 3600
# HTTPCACHE_DIR = "httpcache"
# HTTPCACHE_IGNORE_HTTP_CODES = [503, 504, 400, 401, 403, 404, 408, 429]
# HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Configure AutoThrottle
AUTOTHROTTLE_ENABLED = False  # Disable auto throttle for single URL checks
AUTOTHROTTLE_START_DELAY = 3
AUTOTHROTTLE_MAX_DELAY = 10  # Reduced max delay
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0  # Reduced concurrency
AUTOTHROTTLE_DEBUG = False

# Configure downloader middlewares
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": None,
    "mansion_watch_scraper.middlewares.AntiScrapingMiddleware": 400,
    "mansion_watch_scraper.middlewares.CustomRetryMiddleware": 550,
    "scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware": 810,
    "scrapy.downloadermiddlewares.redirect.RedirectMiddleware": 900,
}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
EXTENSIONS = {}
EXTENSIONS_BASE = {}

# Disable version display
VERSIONS_DISPLAY = False

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
ITEM_PIPELINES = {
    "mansion_watch_scraper.pipelines.MongoPipeline": 300,
    "mansion_watch_scraper.pipelines.SuumoImagesPipeline": 1,
}

# Set settings whose default value is deprecated to a future-proof value
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"

# Set a page count limit for the spider
CLOSESPIDER_PAGECOUNT = 1  # Only scrape one page since we're checking single URLs

# Set mongo db settings
# Change the value of MONGO_URI to "mongodb://localhost:27017" if you are running the MongoDB server locally
# TODO: Change the value of MONGO_URI after deploying the MongoDB server
MONGO_DATABASE = "mansion_watch"
MONGO_URI = os.getenv("MONGO_URI")

# Configure logging to be minimal
LOG_ENABLED = True
LOG_LEVEL = "INFO"
LOG_FORMAT = '{"time": "%(asctime)s", "severity": "%(levelname)s", "message": "%(message)s", "logging.googleapis.com/sourceLocation": {"file": "%(pathname)s", "line": %(lineno)d, "function": "%(funcName)s"}}'
LOG_DATEFORMAT = "%Y-%m-%d %H:%M:%S,000"
LOG_SHORT_NAMES = True
LOG_STDOUT = False
LOG_FILE = None

# Disable only unnecessary logging options
LOG_SPIDER_OPENED = True  # Enable to see spider start/finish
LOG_SPIDER_CLOSED = True
LOG_SCRAPED_ITEMS = False
LOG_UNSCRAPED_ITEMS = False
LOG_DUPLICATE_FILTER = False
LOG_STATS = False
LOG_START_HANDLER = False
VERSIONS_DISPLAY = False
ADDONS_DISPLAY = False
COMMANDS_MODULE = None

# Disable feed exports
FEED_EXPORT_ENABLED = False
FEED_STORAGES = {}
FEED_EXPORTERS = {}
FEED_EXPORT_BATCH_ITEM_COUNT = 0

# Disable specific debug logs
ITEM_SCRAPED_DEBUG = False
ITEM_SCRAPED_INFO = False

# Set the images store
IMAGES_STORE = os.getenv("IMAGES_STORE")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_BUCKET_NAME = os.getenv("GCP_BUCKET_NAME")
GCP_FOLDER_NAME = os.getenv("GCP_FOLDER_NAME")

# Image pipeline settings
IMAGES_URLS_FIELD = "image_urls"
IMAGES_RESULT_FIELD = "images"
