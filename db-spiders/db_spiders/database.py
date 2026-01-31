#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Database connection module for db-spiders

Provides MySQL database connection using PyMySQL
"""

import pymysql

# MySQL Configuration
MYSQL_DB = 'douban'
MYSQL_USER = 'root'
MYSQL_PASS = '1224guoyuanxin'
MYSQL_HOST = 'localhost'

# Create global connection
connection = pymysql.connect(
    host=MYSQL_HOST,
    user=MYSQL_USER,
    password=MYSQL_PASS,
    db=MYSQL_DB,
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor
)
