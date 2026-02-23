#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据清洗 Pipeline
对 MySQL 中的 movies 和 person 表数据进行清洗和标准化，
为后续 Neo4j 导入做准备。

清洗操作直接在 MySQL 中执行（UPDATE），不导出中间文件。
"""

import os
import sys
import pymysql
from dotenv import load_dotenv

SPIDERS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db-spiders')
load_dotenv(os.path.join(SPIDERS_DIR, '.env'))

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '3306')),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASS', '1224guoyuanxin'),
    'db': os.environ.get('DB_NAME', 'douban'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,
}


def get_connection():
    return pymysql.connect(**DB_CONFIG)


def clean_genres(cursor, conn):
    """清洗 genres 字段：去除多余空格，统一分隔符"""
    print("\n🧹 清洗 genres 字段...")

    # 去除前后空格
    cursor.execute("UPDATE movies SET genres = TRIM(genres) WHERE genres IS NOT NULL")
    conn.commit()

    # 去除分隔符前后的空格 (e.g., "剧情 / 喜剧" -> "剧情/喜剧")
    cursor.execute("""
        UPDATE movies 
        SET genres = REPLACE(REPLACE(genres, ' / ', '/'), '/ ', '/')
        WHERE genres IS NOT NULL AND genres LIKE '%% / %%'
    """)
    affected = cursor.rowcount
    conn.commit()
    print(f"  ✅ 统一分隔符: {affected:,} 条记录已更新")

    # 去除末尾的 /
    cursor.execute("""
        UPDATE movies 
        SET genres = TRIM(TRAILING '/' FROM genres)
        WHERE genres IS NOT NULL AND genres LIKE '%%/'
    """)
    conn.commit()

    return affected


def clean_regions(cursor, conn):
    """清洗 regions 字段"""
    print("\n🧹 清洗 regions 字段...")

    cursor.execute("UPDATE movies SET regions = TRIM(regions) WHERE regions IS NOT NULL")
    conn.commit()

    # 统一分隔符
    cursor.execute("""
        UPDATE movies 
        SET regions = REPLACE(REPLACE(regions, ' / ', '/'), '/ ', '/')
        WHERE regions IS NOT NULL AND regions LIKE '%% / %%'
    """)
    affected = cursor.rowcount
    conn.commit()
    print(f"  ✅ 统一分隔符: {affected:,} 条记录已更新")

    return affected


def clean_languages(cursor, conn):
    """清洗 languages 字段"""
    print("\n🧹 清洗 languages 字段...")

    cursor.execute("UPDATE movies SET languages = TRIM(languages) WHERE languages IS NOT NULL")
    conn.commit()

    cursor.execute("""
        UPDATE movies 
        SET languages = REPLACE(REPLACE(languages, ' / ', '/'), '/ ', '/')
        WHERE languages IS NOT NULL AND languages LIKE '%% / %%'
    """)
    affected = cursor.rowcount
    conn.commit()
    print(f"  ✅ 统一分隔符: {affected:,} 条记录已更新")

    return affected


def clean_names(cursor, conn):
    """清洗 name 字段：去除前后空格"""
    print("\n🧹 清洗 name 字段...")

    cursor.execute("UPDATE movies SET name = TRIM(name) WHERE name != TRIM(name)")
    affected_movies = cursor.rowcount
    conn.commit()

    cursor.execute("UPDATE person SET name = TRIM(name) WHERE name != TRIM(name)")
    affected_persons = cursor.rowcount
    conn.commit()

    print(f"  ✅ movies name 清理: {affected_movies:,} 条")
    print(f"  ✅ person name 清理: {affected_persons:,} 条")

    return affected_movies + affected_persons


def clean_scores(cursor, conn):
    """清洗评分数据"""
    print("\n🧹 清洗评分数据...")

    # 将评分为0（无意义）的设为 NULL
    cursor.execute("""
        UPDATE movies SET douban_score = NULL 
        WHERE douban_score = 0
    """)
    zero_scores = cursor.rowcount
    conn.commit()

    # 将评论数为0的设为 NULL
    cursor.execute("""
        UPDATE movies SET douban_votes = NULL 
        WHERE douban_votes = 0
    """)
    zero_votes = cursor.rowcount
    conn.commit()

    print(f"  ✅ 零评分 → NULL: {zero_scores:,} 条")
    print(f"  ✅ 零评论数 → NULL: {zero_votes:,} 条")

    return zero_scores + zero_votes


def clean_actor_director_ids(cursor, conn):
    """验证 actor_ids / director_ids 格式"""
    print("\n🧹 验证 actor_ids / director_ids 格式...")

    # 检查格式是否为 "name:id|name:id"
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM movies 
        WHERE actor_ids IS NOT NULL 
        AND actor_ids != '' 
        AND actor_ids NOT LIKE '%%:%%'
    """)
    bad_actor = cursor.fetchone()['cnt']

    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM movies 
        WHERE director_ids IS NOT NULL 
        AND director_ids != '' 
        AND director_ids NOT LIKE '%%:%%'
    """)
    bad_director = cursor.fetchone()['cnt']

    print(f"  actor_ids 格式异常: {bad_actor:,} 条")
    print(f"  director_ids 格式异常: {bad_director:,} 条")

    if bad_actor > 0:
        # 查看几个异常样例
        cursor.execute("""
            SELECT douban_id, actor_ids FROM movies 
            WHERE actor_ids IS NOT NULL 
            AND actor_ids != '' 
            AND actor_ids NOT LIKE '%%:%%'
            LIMIT 5
        """)
        print("  异常 actor_ids 样例:")
        for row in cursor.fetchall():
            print(f"    {row['douban_id']}: {row['actor_ids'][:80]}")

    # 去除两端空格
    cursor.execute("""
        UPDATE movies SET actor_ids = TRIM(actor_ids)
        WHERE actor_ids IS NOT NULL AND actor_ids != TRIM(actor_ids)
    """)
    conn.commit()
    cursor.execute("""
        UPDATE movies SET director_ids = TRIM(director_ids)
        WHERE director_ids IS NOT NULL AND director_ids != TRIM(director_ids)
    """)
    conn.commit()

    print(f"  ✅ 格式验证完成")
    return bad_actor + bad_director


def clean_empty_strings(cursor, conn):
    """将空字符串统一转为 NULL"""
    print("\n🧹 统一空字符串 → NULL...")

    fields = [
        'alias', 'cover', 'storyline', 'official_site',
        'imdb_id', 'genres', 'directors', 'actors',
        'director_ids', 'actor_ids'
    ]

    total = 0
    for field in fields:
        try:
            cursor.execute(f"UPDATE movies SET `{field}` = NULL WHERE `{field}` = ''")
            affected = cursor.rowcount
            conn.commit()
            if affected > 0:
                print(f"  {field}: {affected:,} 条")
            total += affected
        except Exception as e:
            print(f"  ⚠️ {field}: {e}")

    print(f"  ✅ 共转换: {total:,} 条")
    return total


def print_summary(cursor):
    """打印清洗后的数据概要"""
    print("\n" + "=" * 60)
    print("📊 清洗后数据概要")
    print("=" * 60)

    cursor.execute("SELECT COUNT(*) AS cnt FROM movies")
    print(f"  Movies 总数: {cursor.fetchone()['cnt']:,}")

    cursor.execute("SELECT COUNT(*) AS cnt FROM movies WHERE douban_score IS NOT NULL")
    print(f"  有评分的电影: {cursor.fetchone()['cnt']:,}")

    cursor.execute("SELECT COUNT(*) AS cnt FROM movies WHERE genres IS NOT NULL")
    print(f"  有类型的电影: {cursor.fetchone()['cnt']:,}")

    cursor.execute("SELECT COUNT(*) AS cnt FROM movies WHERE actor_ids IS NOT NULL")
    print(f"  有演员ID的电影: {cursor.fetchone()['cnt']:,}")

    cursor.execute("SELECT COUNT(*) AS cnt FROM movies WHERE director_ids IS NOT NULL")
    print(f"  有导演ID的电影: {cursor.fetchone()['cnt']:,}")

    cursor.execute("SELECT COUNT(*) AS cnt FROM person")
    print(f"  Person 总数: {cursor.fetchone()['cnt']:,}")


def main():
    print("🚀 开始数据清洗 Pipeline...")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        clean_names(cursor, conn)
        clean_genres(cursor, conn)
        clean_regions(cursor, conn)
        clean_languages(cursor, conn)
        clean_scores(cursor, conn)
        clean_empty_strings(cursor, conn)
        clean_actor_director_ids(cursor, conn)
        print_summary(cursor)

        print("\n" + "=" * 60)
        print("✅ 数据清洗完成！")
        print("=" * 60)
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    main()
