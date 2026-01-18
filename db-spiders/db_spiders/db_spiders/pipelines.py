import json
import logging
import os
from datetime import datetime


class JsonWriterPipeline:
    def __init__(self, data_dir):
        """初始化函数"""
        self.data_dir = data_dir  # 数据存储目录
        self.file = None  # 文件对象
        self.items = []  # 存储所有Item的列表
        self.filename = None  # 文件名
        self.crawler = None

    @classmethod
    def from_crawler(cls, crawler):
        data_dir = crawler.settings.get("DATA_DIR", "data/raw")
        pipeline = cls(data_dir)
        pipeline.crawler = crawler
        return pipeline

    def open_spider(self, spider=None):
        os.makedirs(self.data_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if spider is None and self.crawler is not None:
            spider = getattr(self.crawler, "spider", None)

        spider_name = getattr(spider, "name", "spider")
        self.filename = os.path.join(
            self.data_dir, f"movies_{spider_name}_{timestamp}.json"
        )

        self.file = open(self.filename, "w", encoding="utf-8")

        if spider is not None:
            spider.logger.info(f"数据将保存到: {self.filename}")
        else:
            logging.getLogger(__name__).info("数据将保存到: %s", self.filename)

    def close_spider(self, spider=None):
        if self.file is None:
            return

        if spider is None and self.crawler is not None:
            spider = getattr(self.crawler, "spider", None)

        json.dump(self.items, self.file, ensure_ascii=False, indent=2)
        self.file.close()

        if spider is not None:
            spider.logger.info(f"已保存 {len(self.items)} 条数据到 {self.filename}")
            spider.logger.info(f"数据文件路径: {os.path.abspath(self.filename)}")
        else:
            logger = logging.getLogger(__name__)
            logger.info("已保存 %s 条数据到 %s", len(self.items), self.filename)
            logger.info("数据文件路径: %s", os.path.abspath(self.filename))

    def process_item(self, item, spider=None):
        item_dict = dict(item)

        if "crawled_at" not in item_dict:
            item_dict["crawled_at"] = datetime.now().isoformat()

        self.items.append(item_dict)

        return item
