import scrapy


class DoubanMovieItem(scrapy.Item):
    """电影数据项"""

    # 基础信息
    movie_id = scrapy.Field()          # 电影ID
    title = scrapy.Field()             # 电影标题
    original_title = scrapy.Field()    # 原标题
    year = scrapy.Field()              # 上映年份

    # 评分信息
    rating = scrapy.Field()            # 评分
    rating_count = scrapy.Field()     # 评分人数

    # 电影详情
    directors = scrapy.Field()         # 导演列表
    writers = scrapy.Field()           # 编剧列表
    actors = scrapy.Field()            # 演员列表
    genres = scrapy.Field()            # 类型列表

    # 其他信息
    languages = scrapy.Field()         # 语言
    countries = scrapy.Field()         # 制片国家
    release_date = scrapy.Field()      # 上映日期
    duration = scrapy.Field()          # 时长
    summary = scrapy.Field()           # 简介

    # 元数据
    url = scrapy.Field()               # 详情页URL
    image_url = scrapy.Field()         # 封面图片URL
    crawled_at = scrapy.Field()        # 爬取时间
