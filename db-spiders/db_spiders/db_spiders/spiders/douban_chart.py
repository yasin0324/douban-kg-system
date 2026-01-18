import scrapy

from db_spiders.items import DoubanMovieItem


class DoubanChartSpider(scrapy.Spider):
    name = "douban_chart"

    allowed_domains = ["douban.com", "movie.douban.com"]

    start_urls = [
        "https://movie.douban.com/chart",
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 3,  # 下载延迟3秒
    }

    def parse(self, response):
        movie_items = response.css("tr.item")
        self.logger.info(f"找到 {len(movie_items)} 部电影")

        for item in movie_items:
            # 提取电影详情页URL
            movie_url = item.css("a.nbg::attr(href)").get()
            if not movie_url:
                continue
            # 提取电影ID
            movie_id = movie_url.split("/")[-2]
            # 提取电影标题
            title_text = " ".join(
                t.strip() for t in item.css("div.pl2 a::text").getall() if t.strip()
            )
            title = title_text.split("/")[0].strip() if title_text else None
            # 提取评分
            rating = item.css("span.rating_nums::text").get()
            if rating:
                rating = rating.strip()
            # 提取评分人数
            rating_count = item.css("span.rating_nums + span::text").get()
            if rating_count:
                rating_count = rating_count.strip().strip("()").replace("人评价", "")
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

            # 提交数据项
            yield scrapy.Request(
                url=movie_url,
                callback=self.parse_movie_detail,
                meta={"item": movie_item},  # 传递基础Item
            )

    def parse_movie_detail(self, response):
        movie_item = response.meta["item"]
        # 提取原标题
        original_title = response.css('span[property="v:itemreviewed"]::text').get()
        if original_title:
            movie_item["original_title"] = original_title.strip()

        # 定位 #info 区域（包含导演、演员、类型等信息）
        info_div = response.css("#info")

        # 提取导演列表
        directors = info_div.css('a[rel="v:directedBy"]::text').getall()
        if directors:
            movie_item["directors"] = [d.strip() for d in directors]

        # 提取编剧列表
        writers = info_div.css('a[rel="v:writer"]::text').getall()
        if writers:
            movie_item["writers"] = [w.strip() for w in writers]

        # 提取主演列表
        actors = info_div.css('a[rel="v:starring"]::text').getall()
        if actors:
            movie_item["actors"] = [a.strip() for a in actors]

        # 提取类型列表
        genres = info_div.css('span[property="v:genre"]::text').getall()
        if genres:
            movie_item["genres"] = [g.strip() for g in genres]

        # 提取上映日期
        release_date = response.css('span[property="v:initialReleaseDate"]::text').get()
        if release_date:
            movie_item["release_date"] = release_date.strip()

        # 提取年份（从标题旁边的括号中，如 (1994)）
        year = response.css("span.year::text").get()
        if year:
            movie_item["year"] = year.strip("()").strip()

        # 提取时长
        duration = response.css('span[property="v:runtime"]::text').get()
        if duration:
            movie_item["duration"] = duration.strip()

        languages_text = info_div.xpath(
            (
                './/span[@class="pl" and contains(normalize-space(string(.)), '
                '"语言")][1]'
                "/following-sibling::text()[normalize-space()][1]"
            )
        ).get()
        if languages_text:
            movie_item["languages"] = [
                x.strip() for x in languages_text.split("/") if x.strip()
            ]

        countries_text = info_div.xpath(
            (
                './/span[@class="pl" and contains(normalize-space(string(.)), '
                '"制片国家/地区")][1]'
                "/following-sibling::text()[normalize-space()][1]"
            )
        ).get()
        if countries_text:
            movie_item["countries"] = [
                x.strip() for x in countries_text.split("/") if x.strip()
            ]

        # 提取简介
        summary = response.css('span[property="v:summary"]::text').get()
        if summary:
            movie_item["summary"] = summary.strip()
        else:
            # 备用方案：尝试其他选择器
            summary = response.css("div#link-report div.all::text").get()
            if summary:
                movie_item["summary"] = summary.strip()

        title = movie_item.get("title", "未知")
        self.logger.info(f"完成爬取: {title}")

        yield movie_item
