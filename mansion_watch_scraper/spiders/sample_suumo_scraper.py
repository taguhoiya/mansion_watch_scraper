import scrapy

from enums.keys import Keys


class MansionWatchSpider(scrapy.Spider):
    name = "mansion_watch_scraper"
    allowed_domains = ["suumo.jp"]
    start_urls = ["https://suumo.jp/ms/chuko/tokyo/sc_meguro/nc_75709932/"]

    def parse(self, response):
        property_name = (
            response.xpath(
                'normalize-space(//*[@id="mainContents"]/div[4]/div[1]/div[1]/div/h3/text())'
            )
            .get()
            .replace("\u3000", " ")
        )
        property_dict = {
            "property_name": property_name,
        }
        print(property_name)

        # 物件概要
        property_overview = response.xpath(
            '//*[@id="mainContents"]/div[4]/div[1]/div[1]/table/tbody/tr'
        )

        property_overview_dict = {}
        for property_overview_item in property_overview:
            keys = property_overview_item.xpath("th/div/text()").getall()
            normalized_keys = [key.strip() for key in keys if key.strip()]

            values = property_overview_item.xpath("td/text()").getall()
            normalized_values = [value.strip() for value in values if value.strip()]

            for key, value in zip(normalized_keys, normalized_values):
                property_overview_dict[key] = value

        # 共通概要
        common_overview = response.xpath(
            '//*[@id="mainContents"]/div[4]/div[1]/div[2]/table/tbody/tr'
        )

        common_overview_dict = {}
        for common_overview_item in common_overview:
            keys = common_overview_item.xpath("th/div/text()").getall()
            normalized_keys = [key.strip() for key in keys if key.strip()]

            values = common_overview_item.xpath("td/text()").getall()
            normalized_values = [value.strip() for value in values if value.strip()]

            for key, value in zip(normalized_keys, normalized_values):
                if key == Keys.TRAFFIC.value:
                    common_overview_dict[key] = normalized_values
                else:
                    common_overview_dict[key] = value

        # TODO: 会社概要
        # company_overview = response.xpath('//*[@id="mainContents"]/div[5]/div[1]/div[3]/table/tbody/tr')

        # company_overview_items = []
        # for company_overview_item in company_overview:
        #     i = 0

        yield {
            "properties": property_dict,
            "property_overviews": property_overview_dict,
            "common_overviews": common_overview_dict,
        }


# class ScraperSpide(CrawlSpider):
#     name = "scraper"
#     allowed_domains = ["www.scrapingcourse.com"]
#     start_urls = ["https://www.scrapingcourse.com/ecommerce/"]

#     # crawling only the pagination pages, which have the
#     # "https://www.scrapingcourse.com/ecommerce/page/<number>/" format
#     rules = (Rule(LinkExtractor(allow=r"page/\d+/"), callback="parse", follow=True),)

#     def parse(self, response):
#         # get all HTML product elements
#         products = response.css("li.product")
#         # iterate over the list of products
#         for product in products:
#             # since the price elements contain several
#             # text nodes
#             price_text_elements = product.css(".price *::text").getall()
#             price = "".join(price_text_elements)

#             # return a generator for the scraped item
#             yield {
#                 "Url": product.css("a").attrib["href"],
#                 "Image": product.css("img").attrib["src"],
#                 "Name": product.css("h2::text").get(),
#                 "Price": price,
#             }
