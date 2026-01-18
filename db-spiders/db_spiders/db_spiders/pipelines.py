import json
import os
from datetime import datetime


class JsonWriterPipeline:
    def __init__(self, data_dir):
        """初始化函数"""
        self.data_dir = data_dir  # 数据存储目录
        self.file = None  # 文件对象
        self.items = []  # 存储所有Item的列表
        self.filename = None  # 文件名

    @classmethod
    def from_crawler(cls, crawler):
        data_dir = crawler.settings.get("DATA_DIR", "data/raw")
        return cls(data_dir)

    def open_spider(self, spider):
        os.makedirs(self.data_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = os.path.join(
            self.data_dir, f"movies_{spider.name}_{timestamp}.json"
        )

        self.file = open(self.filename, "w", encoding="utf-8")

        spider.logger.info(f"数据将保存到: {self.filename}")

    def close_spider(self, spider):
        json.dump(self.items, self.file, ensure_ascii=False, indent=2)

        self.file.close()

        spider.logger.info(f"已保存 {len(self.items)} 条数据到 {self.filename}")
        spider.logger.info(f"数据文件路径: {os.path.abspath(self.filename)}")

    def process_item(self, item, spider):
        item_dict = dict(item)

        if "crawled_at" not in item_dict:
            item_dict["crawled_at"] = datetime.now().isoformat()

        self.items.append(item_dict)

        return item
