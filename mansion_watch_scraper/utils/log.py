from scrapy.logformatter import LogFormatter


class NoDebugLogFormatter(LogFormatter):
    """A log formatter that filters out debug messages."""

    def dropped(self, item, exception, response, spider):
        """Log when an item is dropped."""
        return {
            "level": "WARNING",
            "msg": "Dropped item: %(exception)s",
            "args": {"exception": exception},
        }

    def scraped(self, item, response, spider):
        """Log when an item is scraped."""
        if "status" in item and item["status"] == "error":
            return {
                "level": "ERROR",
                "msg": "Error scraping item: %(item)s",
                "args": {"item": item},
            }
        return {
            "level": "INFO",
            "msg": "Scraped item: %(item)s",
            "args": {"item": item},
        }

    def download_error(self, failure, request, spider, errmsg=None):
        """Log download errors."""
        return {
            "level": "ERROR",
            "msg": "Error downloading %(request)s: %(errmsg)s",
            "args": {"request": request, "errmsg": errmsg or failure.value},
        }

    def item_error(self, item, exception, response, spider):
        """Log item processing errors."""
        return {
            "level": "ERROR",
            "msg": "Error processing item: %(exception)s",
            "args": {"exception": exception},
        }
