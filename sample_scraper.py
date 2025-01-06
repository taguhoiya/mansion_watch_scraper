from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule

# class ScraperSpider(scrapy.Spider):
#     name = "scraper"
#     allowed_domains = ["www.scrapingcourse.com"]
#     start_urls = ["https://www.scrapingcourse.com/ecommerce/"]

#     def parse(self, response):
#         # get all HTML product elements
#         products = response.css(".propyuct")
#         # iterate over the list of products
#         for product in products:
#             # get the two price text nodes (currency + cost) and
#             # contatenate them
#             price_text_elements = product.css(".price *::text").getall()
#             price = "".join(price_text_elements)

#             # return a generator for the scraped item
#             yield {
#                 "Url": product.css("a").attrib["href"],
#                 "Image": product.css("img").attrib["src"],
#                 "Name": product.css("h2::text").get(),
#                 "Price": price,
#             }

#         # get all pagination link HTML elements
#         pagination_link_elements = response.css("a.page-numbers")

#         # iterate over them to add their URLs to the queue
#         for pagination_link_element in pagination_link_elements:
#             # get the next page URL
#             pagination_link_url = pagination_link_element.attrib["href"]
#             if pagination_link_url:
#                 yield scrapy.Request(
#                     # add the URL to the list
#                     response.urljoin(pagination_link_url)
#                 )


class ScraperSpide(CrawlSpider):
    name = "scraper"
    allowed_domains = ["www.scrapingcourse.com"]
    start_urls = ["https://www.scrapingcourse.com/ecommerce/"]

    # crawling only the pagination pages, which have the
    # "https://www.scrapingcourse.com/ecommerce/page/<number>/" format
    rules = (Rule(LinkExtractor(allow=r"page/\d+/"), callback="parse", follow=True),)

    def parse(self, response):
        # get all HTML product elements
        products = response.css("li.product")
        # iterate over the list of products
        for product in products:
            # since the price elements contain several
            # text nodes
            price_text_elements = product.css(".price *::text").getall()
            price = "".join(price_text_elements)

            # return a generator for the scraped item
            yield {
                "Url": product.css("a").attrib["href"],
                "Image": product.css("img").attrib["src"],
                "Name": product.css("h2::text").get(),
                "Price": price,
            }
