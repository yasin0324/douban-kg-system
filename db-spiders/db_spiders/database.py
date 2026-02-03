#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Database connection module for db-spiders

Provides MySQL database connection using PyMySQL
Supports both local and remote database connections for distributed crawling.

Environment variables (optional, will override defaults):
    DB_HOST: Database server address
    DB_PORT: Database port
    DB_NAME: Database name
    DB_USER: Database username
    DB_PASS: Database password
"""

import os
import pymysql

# MySQL Configuration - can be overridden by environment variables
# 默认连接远程服务器（用于分布式爬取）
MYSQL_HOST = os.environ.get('DB_HOST', '192.168.71.59')
MYSQL_PORT = int(os.environ.get('DB_PORT', '3306'))
MYSQL_DB = os.environ.get('DB_NAME', 'douban')
MYSQL_USER = os.environ.get('DB_USER', 'douban_crawler')
MYSQL_PASS = os.environ.get('DB_PASS', '1224guoyuanxin')

# Connection timeout settings for remote connections
CONNECT_TIMEOUT = 30  # seconds

print(f"[Database] Connecting to {MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB} as {MYSQL_USER}")

# Create global connection
connection = pymysql.connect(
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    user=MYSQL_USER,
    password=MYSQL_PASS,
    db=MYSQL_DB,
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor,
    connect_timeout=CONNECT_TIMEOUT,
    read_timeout=60,
    write_timeout=60,
    autocommit=True  # Important for distributed crawling to avoid lock issues
)

print(f"[Database] Connected successfully!")
