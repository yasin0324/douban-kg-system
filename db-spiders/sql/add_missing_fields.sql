-- 添加缺失字段到movies表

ALTER TABLE `movies`
ADD COLUMN `type` varchar(255) NOT NULL DEFAULT '' AFTER `douban_id`,
ADD COLUMN `cover` varchar(500) DEFAULT NULL AFTER `alias`,
ADD COLUMN `slug` varchar(255) NOT NULL DEFAULT '' AFTER `type`,
ADD COLUMN `directors` varchar(500) DEFAULT NULL AFTER `release_date`,
ADD COLUMN `actors` text DEFAULT NULL AFTER `directors`,
ADD COLUMN `official_site` varchar(500) DEFAULT NULL AFTER `languages`,
ADD COLUMN `imdb_id` varchar(255) DEFAULT NULL AFTER `mins`,
ADD COLUMN `tags` varchar(500) DEFAULT NULL AFTER `imdb_id`;

-- 为新字段添加索引(可选)
ALTER TABLE `movies`
ADD INDEX `idx_type` (`type`),
ADD INDEX `idx_slug` (`slug`);
