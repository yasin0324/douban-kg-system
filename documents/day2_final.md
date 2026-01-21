---

# 🎯 第二天开始：全面采集豆瓣电影数据（电影+演员+评论）

## 📚 第二天学习目标

仿照成熟的 **AntSpider** 项目，学习并实现**四阶段数据采集架构**，全面采集豆瓣电影数据：电影元数据、演员/导演信息、评论数据。

### 为什么学习 AntSpider 项目？

**AntSpider** 是一个经过实战验证的豆瓣爬虫项目：
- 数据规模：13万+ 电影、350万+ 评论
- 架构成熟：四阶段数据流，支持增量处理
- 抗封能力强：随机 bid cookie + UA 轮换 + 代理池
- 生产可用：单机一晚上可完成全量爬取（配代理）

### 第二天新计划

上午任务（2–3 小时）：
- [ ] 理解四阶段爬虫架构
- [ ] 设计 MySQL 数据库表结构
- [ ] 实现 Stage 1：收集电影 Subject IDs
- [ ] 实现 Stage 2：爬取电影元数据

下午任务（2–3 小时）：
- [ ] 实现 Stage 3：爬取演员/导演信息
- [ ] 实现 Stage 4：爬取电影评论
- [ ] 实现反爬中间件
- [ ] 数据验证脚本
- [ ] 运行完整流程

---

## 第八部分：四阶段架构总览

### 数据流动过程

```
1️⃣ Stage 1: Subject Collection
   movie_subject → subjects 表 (douban_id, type)
                ↓
2️⃣ Stage 2: Meta Extraction
   movie_meta → movies 表 (含 actor_ids, director_ids)
                ↓
3️⃣ 中间处理：提取 Person IDs
   从 movies 表提取 person_ids → person_obj 表（临时）
                ↓
4️⃣ Stage 3: Person Metadata
   person_meta → person 表 (演员/导演详细信息)
                ↓
5️⃣ Stage 4: Comment Scraping
   movie_comment → comments 表
```

### 核心设计理念

1. **增量处理**：每次只爬取未处理的数据
2. **数据库驱动**：从数据库读取待爬取URL
3. **反爬策略**：随机 bid cookie + UA 轮换 + 请求延迟
4. **容错机制**：响应体大小检测 + 状态码处理

---

## 第九部分：数据库设计（MySQL）

### 表结构设计（关键部分）

```sql
-- subjects 表：存储电影 subject_id
CREATE TABLE subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    douban_id VARCHAR(20) UNIQUE NOT NULL,
    type VARCHAR(20) NOT NULL DEFAULT 'movie',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- movies 表：存储电影详细信息（21个字段）
CREATE TABLE movies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    douban_id VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(255),
    directors TEXT,              -- '诺兰/克里斯托弗·诺兰'
    director_ids TEXT,          -- '诺兰:1049971|张三:123456'
    actors TEXT,
    actor_ids TEXT,
    genres TEXT,                 -- '剧情/科幻/冒险'
    douban_score DECIMAL(3,1),
    douban_votes INT,
    storyline TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- person 表：存储人物详细信息
CREATE TABLE person (
    id INT AUTO_INCREMENT PRIMARY KEY,
    person_id VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(255),
    profession TEXT,
    biography TEXT
);

-- comments 表：存储评论
CREATE TABLE comments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    douban_id VARCHAR(20) NOT NULL,
    user_nickname VARCHAR(255),
    content TEXT,
    votes INT,
    rating VARCHAR(20)
);
```

### 数据存储格式约定

1. **列表字段**：使用斜杠 `/` 分隔
   ```
   directors = "诺兰/克里斯托弗·诺兰"
   genres = "剧情/科幻/冒险"
   ```

2. **关联ID字段**：使用竖线 `|` 分隔，格式为 `姓名:id`
   ```
   director_ids = "诺兰:1049971|张三:123456"
   
   # 解析
   for entry in director_ids.split('|'):
       name, person_id = entry.split(':')
   ```

---

## 第十部分：Stage 1 - 收集电影 Subject IDs

### 爬虫设计思路

**目标**：从豆瓣页面收集尽可能多的电影 `douban_id`

**使用技术**：
- `CrawlSpider`：自动跟随链接
- `LinkExtractor`：定义提取规则
- 增量处理：避免重复收集

### 关键代码结构

```python
"""爬虫：douban_subject.py"""
from scrapy.spiders import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor

class DoubanSubjectSpider(CrawlSpider):
    name = "movie_subject"
    allowed_domains = ["douban.com", "movie.douban.com"]
    
    # 使用豆瓣标签页作为起点
    start_urls = ["https://movie.douban.com/tag/#/?sort=S&range=0,10&tags=电影"]
    
    # 关键：定义提取规则
    rules = (
        Rule(LinkExtractor(allow=r'/subject/\d+/'), callback='parse_item', follow=True),
    )
    
    def parse_item(self, response):
        """从 URL 中提取 douban_id"""
        if len(response.body) < 10000:
            return
        
        parts = response.url.split("subject")[1].split("/")
        douban_id = parts[1]
        
        if douban_id.isdigit():
            item = Subject()
            item["douban_id"] = douban_id
            item["type"] = "movie"
            yield item
```

---

## 第十一部分：Stage 2 - 爬取电影元数据

### 爬虫设计思路

**目标**：根据 `subject_id` 爬取电影详细信息，包含演员/导演ID

**关键技术**：
- 数据库驱动：从 subjects 表读取未爬取的 `douban_id`
- XPath 提取：提取 21 个字段
- ID 格式化：将姓名和 ID 组合为 `'姓名:id'` 格式

### 关键代码结构

```python
"""爬虫：douban_meta.py"""
import pymysql

class DoubanMetaSpider(scrapy.Spider):
    name = "movie_meta"
    
    def start_requests(self):
        """从数据库读取待爬取的 subject_id"""
        self.cursor.execute("""
            SELECT douban_id FROM subjects 
            WHERE douban_id NOT IN (SELECT douban_id FROM movies)
            LIMIT 1000
        """)
        
        for row in self.cursor.fetchall():
            douban_id = row[0]
            url = f"https://movie.douban.com/subject/{douban_id}/"
            yield Request(url, cookies=self.generate_bid())
    
    def parse(self, response):
        """解析电影详情页"""
        item = MovieMeta()
        item["douban_id"] = response.url.split("/")[-2]
        item["name"] = response.xpath('//span[@property="v:itemreviewed"]/text()').get()
        
        # ========== 提取导演（含ID）- 关键逻辑 ==========
        director_names = response.xpath('//a[@rel="v:directedBy"]/text()').getall()
        director_urls = response.xpath('//a[@rel="v:directedBy"]/@href').getall()
        
        director_ids = []
        for i, name in enumerate(director_names):
            if i < len(director_urls):
                url_parts = director_urls[i].split("celebrity")[1].split("/")
                director_ids.append(f"{name}:{url_parts[1]}")
        
        item["director_ids"] = "|".join(director_ids)
        
        # ========== 提取演员（同上逻辑）==========
        # ... 类似代码提取 actors 和 actor_ids
        
        # ========== 其他字段 ==========
        item["genres"] = "/".join(response.xpath('//span[@property="v:genre"]/text()').getall())
        item["douban_score"] = response.xpath('//strong[@property="v:average"]/text()').get()
        
        yield item
```

### 关键XPath模式说明

```python
# 提取标签后的文本（如：制片国家/地区: 美国/英国）
'//text()[preceding-sibling::span[text()="制片国家/地区:"]][following-sibling::br]'

# 提取属性值
'//img[@rel="v:image"]/@src'  # 封面图片URL
'//span[@property="v:runtime"]/@content'  # 时长

# 提取多个元素
'//a[@rel="v:directedBy"]/text()'  # 所有导演名称
'//span[@property="v:genre"]/text()'  # 所有类型
```

---

## 第十二部分：中间处理 - 提取 Person IDs

### 脚本设计思路

**目标**：从 `movies` 表的 `actor_ids` 和 `director_ids` 字段提取 `person_id`，存入 `person_obj` 表

**输入格式**：`'诺兰:1049971|张三:123456|李四:789012'`

**输出格式**：`person_obj` 表 (person_id, person_name, source_type)

### 关键代码

```python
"""脚本：rebuild_pid.py"""
import pymysql

# 提取 director_ids
cursor.execute("SELECT director_ids FROM movies WHERE director_ids IS NOT NULL AND director_ids != ''")
for row in cursor.fetchall():
    director_ids_str = row[0]
    for entry in director_ids_str.split('|'):
        if ':' in entry:
            name, person_id = entry.split(':')
            cursor.execute("""
                INSERT IGNORE INTO person_obj (person_id, person_name, source_type)
                VALUES (%s, %s, 'director')
            """, (person_id.strip(), name.strip()))

# 提取 actor_ids
cursor.execute("SELECT actor_ids FROM movies WHERE actor_ids IS NOT NULL AND actor_ids != ''")
for row in cursor.fetchall():
    actor_ids_str = row[0]
    for entry in actor_ids_str.split('|'):
        if ':' in entry:
            name, person_id = entry.split(':')
            cursor.execute("""
                INSERT IGNORE INTO person_obj (person_id, person_name, source_type)
                VALUES (%s, %s, 'actor')
            """, (person_id.strip(), name.strip()))

print("✅ Person IDs 已提取到 person_obj 表")
```

---

## 第十三部分：Stage 3 - 爬取演员/导演信息

### 爬虫设计思路

**目标**：根据 `person_id` 爬取演员/导演详细信息

**关键技术**：
- 数据库驱动：从 `person_obj` 表读取未爬取的 `person_id`
- 人物详情页 URL：`https://movie.douban.com/celebrity/{person_id}/`

### 关键代码结构

```python
"""爬虫：douban_person.py"""
import pymysql

class DoubanPersonSpider(scrapy.Spider):
    name = "person_meta"
    
    def start_requests(self):
        """从 person_obj 表读取待爬取的 person_id"""
        self.cursor.execute("""
            SELECT person_id FROM person_obj 
            WHERE person_id NOT IN (SELECT person_id FROM person)
            LIMIT 500
        """)
        
        for row in self.cursor.fetchall():
            person_id = row[0]
            url = f"https://movie.douban.com/celebrity/{person_id}/"
            yield Request(url, cookies=self.generate_bid())
    
    def parse(self, response):
        """解析人物详情页"""
        it
