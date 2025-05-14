import scrapy
import re
import logging
import datetime
from dateutil import parser as date_parser


class F1MotorsportSpider(scrapy.Spider):
    name = "motorsport"
    allowed_domains = ["www.motorsport.com"]
    start_urls = [
        'https://www.motorsport.com/f1/news/?filters%5Brace_type%5D%5B%5D=54&filters%5Barticle_type%5D%5B%5D=19', # Analysis
        'https://www.motorsport.com/f1/news/?filters%5Brace_type%5D%5B%5D=54&filters%5Barticle_type%5D%5B%5D=17', # Blog
        'https://www.motorsport.com/f1/news/?filters%5Brace_type%5D%5B%5D=54&filters%5Barticle_type%5D%5B%5D=12', # Commentary
        'https://www.motorsport.com/f1/news/?filters%5Brace_type%5D%5B%5D=54&filters%5Barticle_type%5D%5B%5D=48', # Opinion
        'https://www.motorsport.com/f1/news/?filters%5Brace_type%5D%5B%5D=54&filters%5Barticle_type%5D%5B%5D=18', # Special feature
    ]

    # Custom logging settings for this spider
    custom_settings = {
        'LOG_FILE': 'logs/motorsport_spider.log',  # Custom log file for F1MotorsportSpider
        'LOG_LEVEL': 'INFO',  # Log level (can be DEBUG, INFO, WARNING, ERROR)
        'LOG_FORMAT': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Log format
        'LOG_ENCODING': 'utf-8',  # Ensure UTF-8 encoding for the log file
    }

    def __init__(self, name=None, **kwargs):
        super().__init__(name, **kwargs)
        self.start_date = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(url, meta={"playwright": True, "playwright_include_page": True})

    async def parse(self, response):
        page = response.meta["playwright_page"]
        self.logger.info(f"Processing {response.url}")
        while True:
            article_data = await page.query_selector_all(".ms-content__main a.ms-item:not(.ms-item--prime)")
            num_articles = len(article_data)
            self.logger.info(f"Found {num_articles} article headers so far.")

            if num_articles == 0:
                self.logger.info("No articles found, stopping pagination.")
                break

            last_article = article_data[-1]
            published_time = await last_article.query_selector(".ms-item__date")
            if published_time:
                published_datetime = await published_time.get_attribute("datetime")
                if published_datetime:
                    try:
                        last_article_date = date_parser.parse(published_datetime)
                        self.logger.info(f"Last article date: {last_article_date}")
                        # If the last article is still newer than the cutoff, we want to load more.
                        if last_article_date >= self.start_date:
                            self.logger.info("Last article is newer than cutoff. Clicking load more...")
                        else:
                            self.logger.info("Last article is older than cutoff. Stopping pagination.")
                            break
                    except Exception as e:
                        self.logger.error(f"Error parsing date: {e}")
                        break
                else:
                    self.logger.info("No published datetime attribute found in the last article, stopping pagination.")
                    break
            else:
                self.logger.info("No published time element found in the last article, stopping pagination.")
                break

            # Attempt to locate the load more button.
            load_more_button = await page.query_selector("a.msnt-button--neutral")
            if load_more_button:
                self.logger.info("Clicking the load more button...")
                await load_more_button.click()
                # Wait briefly for the new content to load and for the URL to update.
                await page.wait_for_timeout(120000)
                self.logger.info(f"New URL after load more: {page.url}")
            else:
                self.logger.info("No load more button found. Ending pagination.")
                break

        # After finishing pagination, capture the full HTML content.
        full_html = await page.content()
        new_response = response.replace(body=full_html)
        await page.close()

        # You can now process new_response to extract article links or perform other parsing.
        articles = new_response.css(".ms-content__main a.ms-item:not(.ms-item--prime)")

        for article in articles:
            article_datetime = date_parser.parse(article.css(".ms-item__date::attr(datetime)").get())
            if article_datetime >= self.start_date:
                link = article.css("::attr(href)").get()
                relative_url = 'https://www.motorsport.com' + link
                yield response.follow(relative_url, meta={'playwright': True}, callback=self.parse_new_article)
        

    async def parse_new_article(self, response):
        page = response.meta["playwright_page"]
        self.logger.info(f"Loading comments for {response.url}")

         # 1) Trigger the JS to load all comments
        await self.parse_article_comments(page)
        # 2) Grab the fully‑rendered comments HTML
        comments_html = await page.content()
        await page.close()

        # 3) Parse comments with a fresh Scrapy selector
        comment_sel = scrapy.Selector(text=comments_html)
        comments = []
        for c in comment_sel.css(".comment-item"):
            author = c.css(".comment-author::text").get(default="").strip()
            text   = c.css(".comment-text::text").get(default="").strip()

            # replies
            replies = []
            for r in c.css(".reply-item"):
                r_author = r.css(".reply-author::text").get(default="").strip()
                r_text   = r.css(".reply-text::text").get(default="").strip()
                replies.append({"author": r_author, "text": r_text})

            comments.append({
                "author":  author,
                "text":    text,
                "replies": replies
            })

        # Extract detailed article information from the article page.
        article_type = response.css(".msnt-badge--accent > span:nth-child(1)::text").get()
        
        title = response.css("h1.text-h1::text").get()
        if title:
            title = title.replace("\n", " ").strip()
        
        article_description = response.css("h2.text-article-description::text").get()
        if article_description:
            article_description = article_description.replace("\n", " ").strip()
        
        authors = response.css("a.text-controls-md::text").getall()
        
        published_datetime = response.css("time.text-footnote-md::attr(datetime)").get()
        updated_datetime = response.css("time.ms-date-with-timezone:nth-child(2)::attr(datetime)").get()

        content = response.css(".ms-article-content p *::text").getall()
        excluded_text = response.css(".ms-article-content p.title::text, .ms-article-content p.photographer::text").getall()
        filtered_text = [text for text in content if text not in excluded_text]
        article_text = re.sub(r'\s+', ' ', " ".join(filtered_text)).strip()

        # Fix encoding issues in article text
        article_text = article_text.encode('utf-8', 'ignore').decode('utf-8')  # Handle encoding issues


        yield {
            "article_type": article_type,
            "title": title,
            "article_description": article_description,
            "authors": authors,
            "url": response.url,
            "content": article_text,    
            "original_datetime": published_datetime,
            "updated_datetime": updated_datetime if updated_datetime else None,
            "comments": comments,
        }

    async def parse_article_comments(self, page):
        btn = await page.query_selector("button.msnt-button--prime")
        if not btn:
            self.logger.info("No ‘View all comments’ button found.")
            return

        self.logger.info("Clicking ‘View all comments’…")
        await btn.click()
        # wait until at least one comment loads
        await page.wait_for_selector(".comment-item", timeout=30000)
        self.logger.info("Comments are now rendered.")