import scrapy
import re
import json
import urllib.parse

class SampleArticleSpider(scrapy.Spider):
    name = "sample_motorsport"
    allowed_domains = ["www.motorsport.com", "www-coral.motorsport.com"]
    start_urls = [
        "https://www.motorsport.com/f1/news/zak-brown-took-over-a-broken-mclaren-heres-how-he-fixed-it/10714812/",
        "https://www.motorsport.com/f1/news/lewis-hamilton-32-second-interview-sums-up-his-saudi-shocker/10715535/"
    ]

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta={"playwright": True, "playwright_include_page": True},
                callback=self.parse_article,
            )

    @staticmethod
    def construct_coral_api_url(story_url):
        match = re.search(r'/(\d+)/?$', story_url)
        if not match:
            print("No article ID found.")
            return None
        
        article_id = match.group(1)
        story_id = "article__" + article_id
        
        base_url = "https://www-coral.motorsport.com/api/graphql"
        graphql_id = "02516fe97b04a849a15fb09fe913e502"

        variables = {
            "storyID": story_id,
            "storyURL": story_url,
            "commentsOrderBy": "REACTION_DESC",
            "tag": None,
            "storyMode": None,
            "flattenReplies": True,
            "ratingFilter": None,
            "refreshStream": False
        }

        variables_json = json.dumps(variables)
        variables_encoded = urllib.parse.quote(variables_json)
        final_url = f"{base_url}?query=&id={graphql_id}&variables={variables_encoded}"

        return final_url
    
    def parse_comments(self, response):
        article_data = response.meta["article_data"]
        
        try:
            data = json.loads(response.text)
            # Get top-level VALUES (not keys) of the JSON
            parent_values = list(data.values())
            article_data["comments_parent_values"] = parent_values
        except Exception as e:
            article_data["comments_parent_values"] = []
            self.logger.error(f"Failed to parse comments: {e}")
        
        yield article_data

    def parse_article(self, response):
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
        article_text = article_text.encode('utf-8', 'ignore').decode('utf-8')

        # Construct and include the comments link (no request made)
        comments_api_url = self.construct_coral_api_url(response.url)

        article_data = {
            "article_type": article_type,
            "title": title,
            "article_description": article_description,
            "authors": authors,
            "url": response.url,
            "content": article_text,    
            "original_datetime": published_datetime,
            "updated_datetime": updated_datetime if updated_datetime else None
        }

        if comments_api_url:
            # Make request to comments API and pass article_data forward
            yield scrapy.Request(
                comments_api_url,
                callback=self.parse_comments,
                meta={"article_data": article_data}
            )
        else:
            # If no comment URL, yield without comments data
            article_data["comments_parent_values"] = []
            yield article_data