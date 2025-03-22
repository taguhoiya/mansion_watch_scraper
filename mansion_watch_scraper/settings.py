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
ROBOTSTXT_OBEY = True

# Configure maximum concurrent requests performed by Scrapy (default: 16)
CONCURRENT_REQUESTS = 1

# Configure a delay for requests for the same website (default: 0)
DOWNLOAD_DELAY = 5  # Increase delay between requests
RANDOMIZE_DOWNLOAD_DELAY = True  # Add randomization to delays

# Disable cookies (enabled by default)
COOKIES_ENABLED = True
COOKIES_DEBUG = False

# Disable Telnet Console (enabled by default)
# TELNETCONSOLE_ENABLED = False

# Override the default request headers:
# DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
# }

# Configure spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
# SPIDER_MIDDLEWARES = {
#    "mansion_watch_scraper.middlewares.MansionWatchScraperSpiderMiddleware": 543,
# }

# Configure retry settings
RETRY_ENABLED = True
RETRY_TIMES = 8  # Increase retry attempts
RETRY_HTTP_CODES = [
    500,
    502,
    503,
    504,
    522,
    524,
    408,
    429,
    302,
    301,
    303,
    307,
    308,
    403,
    404,
]

# Configure download settings
DOWNLOAD_TIMEOUT = 90  # Increase timeout

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
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 5
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
AUTOTHROTTLE_DEBUG = False

# Configure downloader middlewares
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": None,
    "mansion_watch_scraper.middlewares.AntiScrapingMiddleware": 400,
    "mansion_watch_scraper.middlewares.CustomRetryMiddleware": 550,
}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
# EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
# }

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
CLOSESPIDER_PAGECOUNT = 10

# Set mongo db settings
# Change the value of MONGO_URI to "mongodb://localhost:27017" if you are running the MongoDB server locally
# TODO: Change the value of MONGO_URI after deploying the MongoDB server
MONGO_DATABASE = "mansion_watch"
MONGO_URI = os.getenv("MONGO_URI")

# Set the log level
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")

# Set the images store
IMAGES_STORE = os.getenv("IMAGES_STORE")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_BUCKET_NAME = os.getenv("GCP_BUCKET_NAME")
GCP_FOLDER_NAME = os.getenv("GCP_FOLDER_NAME")

# Image pipeline settings
IMAGES_URLS_FIELD = "image_urls"
IMAGES_RESULT_FIELD = "images"
