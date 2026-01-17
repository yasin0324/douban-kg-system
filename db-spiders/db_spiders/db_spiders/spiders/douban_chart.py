import scrapy
from db_spiders.items import DoubanMovieItem

class DoubanChartSpider(scrapy.Spider):
    name = "douban_chart"

    allowed_domains = ["douban.com", "movie.douban.com"]

    start_urls = [
        "https://movie.douban.com/chart",
    ]
    
    custom_settings = {
        "DOWNLOAD_DELAY": 3,    # 下载延迟3秒
    }
    
    def parse(self, response):
        movie_items = response.css('tr.item')
        
        self.logger.info(f"找到 {len(movie_items)} 部电影")
        
        for item in movie_items:
            # 提取电影详情页URL
            movie_url = item.css('a.nbg::attr(href)').get()
            if not movie_url:
                continue
            # 提取电影ID
            movie_id = movie_url.split('/')[-2]
            # 提取电影标题
            title = item.css('div.pl2 a::text').get()
            if title:
                title = title.strip()   # 去掉首尾空格
            # 提取评分
            rating = item.css('span.rating_nums::text').get()
            if rating:
                rating = rating.strip()
            # 提取评分人数
            rating_count = item.css('span.rating_nums + span::text').get()
            if rating_count:
                rating_count = rating_count.strip().strip('()').replace("人评价", "")
            # 提取封面图片url
            image_url = item.css("a.nbg img::attr(src)").get()
            
            # 创建数据项
            movie_item = DoubanMovieItem()
            movie_item["movie_id"] = movie_id
            movie_item["title"] = title
            movie_item["rating"] = rating
            movie_item["rating_count"] = rating_count
            movie_item["url"] = movie_url
            movie_item["image_url"] = image_url
            
            # 输出日志
            self.logger.info(f"发现电影: {title} (ID: {movie_id}, 评分: {rating})")
            
            # 提交数据项
            yield movie_item