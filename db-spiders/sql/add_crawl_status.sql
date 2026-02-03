-- 为分布式爬取添加状态字段
-- 防止多台电脑重复爬取同一个电影

-- 在 subjects 表添加爬取状态字段
ALTER TABLE `subjects`
ADD COLUMN `crawl_status` TINYINT NOT NULL DEFAULT 0 COMMENT '爬取状态: 0=待爬, 1=爬取中, 2=已完成, 3=失败',
ADD COLUMN `crawl_locked_at` DATETIME DEFAULT NULL COMMENT '锁定时间（用于超时释放）',
ADD COLUMN `crawl_worker` VARCHAR(100) DEFAULT NULL COMMENT '爬取的worker标识';

-- 添加索引加速查询
ALTER TABLE `subjects`
ADD INDEX `idx_crawl_status` (`crawl_status`, `type`);

-- 重置超时的锁（超过30分钟未完成的任务）
-- 可以定期执行此SQL释放卡住的任务
-- UPDATE subjects SET crawl_status = 0, crawl_locked_at = NULL, crawl_worker = NULL 
-- WHERE crawl_status = 1 AND crawl_locked_at < NOW() - INTERVAL 30 MINUTE;
