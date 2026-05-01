-- MySQL schema evidence for thesis planning
-- Generated: 2026-05-01
-- Source database: douban
-- Method: SHOW CREATE TABLE from the current MySQL instance
-- Passwords and connection secrets are not included.

-- ============================================================
-- Table: subjects
-- Rows: 192035
-- ============================================================
CREATE TABLE `subjects` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `douban_id` int NOT NULL COMMENT '豆瓣电影ID',
  `type` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT 'movie' COMMENT '类型: movie',
  `status` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT 'pending',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `crawl_status` tinyint NOT NULL DEFAULT '0' COMMENT '爬取状态: 0=待爬, 1=爬取中, 2=已完成, 3=失败',
  `crawl_locked_at` datetime DEFAULT NULL COMMENT '锁定时间',
  `crawl_worker` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'worker标识',
  PRIMARY KEY (`id`),
  UNIQUE KEY `douban_id` (`douban_id`),
  KEY `idx_status` (`status`),
  KEY `idx_type` (`type`),
  KEY `idx_crawl_status` (`crawl_status`,`type`)
) ENGINE=InnoDB AUTO_INCREMENT=1426816 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='电影ID种子表';

-- ============================================================
-- Table: movies
-- Rows: 192032
-- ============================================================
CREATE TABLE `movies` (
  `douban_id` int NOT NULL COMMENT '豆瓣电影ID',
  `type` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '电影名称',
  `alias` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '别名',
  `cover` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `year` smallint DEFAULT NULL COMMENT '上映年份',
  `genres` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '类型（逗号分隔）',
  `regions` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '制片国家/地区',
  `languages` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '语言',
  `official_site` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `mins` smallint DEFAULT NULL COMMENT '片长（分钟）',
  `imdb_id` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `storyline` text COLLATE utf8mb4_unicode_ci COMMENT '剧情简介',
  `douban_score` decimal(3,1) DEFAULT NULL COMMENT '豆瓣评分',
  `douban_votes` int DEFAULT NULL COMMENT '评分人数',
  `release_date` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '上映日期',
  `directors` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `actors` text COLLATE utf8mb4_unicode_ci,
  `actor_ids` text COLLATE utf8mb4_unicode_ci COMMENT '演员ID列表（格式: 姓名:ID,姓名:ID）',
  `director_ids` text COLLATE utf8mb4_unicode_ci COMMENT '导演ID列表（格式: 姓名:ID,姓名:ID）',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`douban_id`),
  KEY `idx_year` (`year`),
  KEY `idx_score` (`douban_score`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='电影元数据表';

-- ============================================================
-- Table: person
-- Rows: 236882
-- ============================================================
CREATE TABLE `person` (
  `person_id` int NOT NULL,
  `name` varchar(255) NOT NULL,
  `sex` enum('男','女') DEFAULT NULL,
  `name_en` varchar(500) DEFAULT NULL,
  `name_zh` varchar(500) DEFAULT NULL,
  `birth` date DEFAULT NULL,
  `death` date DEFAULT NULL,
  `birthplace` varchar(255) DEFAULT NULL,
  `profession` varchar(255) DEFAULT NULL,
  `biography` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`person_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- Table: person_obj
-- Rows: 236890
-- ============================================================
CREATE TABLE `person_obj` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `person_id` int NOT NULL COMMENT '豆瓣人物ID',
  `name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '人物姓名（可选，来自movies表）',
  `status` tinyint DEFAULT '0' COMMENT '采集状态: 0=待采集, 1=已采集, 2=采集失败',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `person_id` (`person_id`),
  KEY `idx_status` (`status`),
  KEY `idx_person_obj_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=236891 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='待采集人物ID表';

-- ============================================================
-- Table: users
-- Rows: 518
-- ============================================================
CREATE TABLE `users` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `nickname` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `avatar_url` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` enum('active','banned','deleted') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `is_mock` tinyint(1) NOT NULL DEFAULT '0',
  `last_login_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`),
  KEY `idx_users_status_created` (`status`,`created_at`),
  KEY `idx_users_is_mock_status` (`is_mock`,`status`)
) ENGINE=InnoDB AUTO_INCREMENT=1096 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Table: user_sessions
-- Rows: 89
-- ============================================================
CREATE TABLE `user_sessions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `refresh_token_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_agent` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ip_address` varchar(45) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `expires_at` datetime NOT NULL,
  `revoked_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `refresh_token_hash` (`refresh_token_hash`),
  KEY `idx_user_sessions_user` (`user_id`,`created_at`),
  KEY `idx_user_sessions_expires` (`expires_at`),
  CONSTRAINT `user_sessions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=106 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Table: user_movie_prefs
-- Rows: 84983
-- ============================================================
CREATE TABLE `user_movie_prefs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `mid` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '映射 movies.douban_id',
  `pref_type` enum('like','want_to_watch') COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_mid` (`user_id`,`mid`),
  KEY `idx_user_pref_type` (`user_id`,`pref_type`),
  KEY `idx_mid_pref_type` (`mid`,`pref_type`),
  CONSTRAINT `user_movie_prefs_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=96941 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Table: user_movie_ratings
-- Rows: 107076
-- ============================================================
CREATE TABLE `user_movie_ratings` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `mid` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '映射 movies.douban_id',
  `rating` decimal(2,1) NOT NULL COMMENT '0.5 - 5.0',
  `comment_short` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `rated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_mid_rating` (`user_id`,`mid`),
  KEY `idx_mid_rating` (`mid`,`rating`),
  KEY `idx_user_rated_at` (`user_id`,`rated_at`),
  CONSTRAINT `user_movie_ratings_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=131768 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Table: user_search_history
-- Rows: 0
-- ============================================================
CREATE TABLE `user_search_history` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint DEFAULT NULL,
  `query_text` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_count` int NOT NULL DEFAULT '0',
  `searched_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_searched_at` (`user_id`,`searched_at`),
  KEY `idx_query_text` (`query_text`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Table: admins
-- Rows: 0
-- ============================================================
CREATE TABLE `admins` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` enum('super_admin','admin','auditor') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'admin',
  `status` enum('active','disabled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `last_login_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  KEY `idx_admin_status_role` (`status`,`role`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Table: admin_sessions
-- Rows: 0
-- ============================================================
CREATE TABLE `admin_sessions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `admin_id` bigint NOT NULL,
  `refresh_token_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ip_address` varchar(45) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `user_agent` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `expires_at` datetime NOT NULL,
  `revoked_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `refresh_token_hash` (`refresh_token_hash`),
  KEY `idx_admin_sessions_admin` (`admin_id`,`created_at`),
  CONSTRAINT `admin_sessions_ibfk_1` FOREIGN KEY (`admin_id`) REFERENCES `admins` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Table: admin_user_actions
-- Rows: 0
-- ============================================================
CREATE TABLE `admin_user_actions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `admin_id` bigint NOT NULL,
  `target_user_id` bigint NOT NULL,
  `action_type` enum('ban_user','unban_user','force_logout','reset_password','update_profile','delete_user') COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metadata_json` json DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_admin_action_time` (`admin_id`,`created_at`),
  KEY `idx_target_action_time` (`target_user_id`,`created_at`),
  CONSTRAINT `admin_user_actions_ibfk_1` FOREIGN KEY (`admin_id`) REFERENCES `admins` (`id`),
  CONSTRAINT `admin_user_actions_ibfk_2` FOREIGN KEY (`target_user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
