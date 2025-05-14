from pathlib import Path

import scrapy


class QuotesSpider(scrapy.Spider):
    name = "quotes"

    def start_requests(self):
        urls = [
            "https://quotes.toscrape.com/page/1/",
            "https://quotes.toscrape.com/page/2/",
        ]

        # Using start_requests method will generate scrapy.Request objects
        for url in urls:
            yield scrapy.Request(url=url, callback=self.parse)

    # parse method is default callback method
    def parse(self, response):
        for quote in response.css("div.quote"):
            yield {
                "text": quote.css("span.text::text").get(),
                "author": quote.css("small.author::text").get(),
                "tags": quote.css("div.tags a.tag::text").getall(),
            }


# Alternative to the start_requests method
# class QuotesSpider(scrapy.Spider):
#     name = "quotes"

#     # start_urls is a class attribute that can be used to create initial requests for spider
#     start_urls = [
#         "https://quotes.toscrape.com/page/1/",
#         "https://quotes.toscrape.com/page/2/",
#     ]

#     def parse(self, response):
#         page = response.url.split("/")[-2]
#         filename = f"quotes-{page}.html"
#         Path(filename).write_bytes(response.body)
#         self.log(f"Saved file {filename}")

