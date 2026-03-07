#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重爬不完整电影数据

找出 movies 表中有评分（douban_score IS NOT NULL）且有一定评分人数
（douban_votes >= min_votes），但 cover 或 storyline 为空的记录。

操作步骤：
    1. 删除 movies 表中这些不完整记录
    2. 将 subjects 表中对应记录的 crawl_status 重置为 0

这样 proxy_crawler.py 的 fetch_open_tasks() 的
LEFT JOIN ... WHERE m.douban_id IS NULL 条件就能重新选中它们。

使用方法:
    1. 先运行此脚本：uv run python db-spiders/recrawl_incomplete_movies.py
    2. 再运行爬虫：uv run python db-spiders/proxy_crawler.py --direct --update
"""

import argparse
import pymysql
import sys

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '1224guoyuanxin',
    'db': 'douban',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}


def main():
    parser = argparse.ArgumentParser(description='重爬不完整电影数据')
    parser.add_argument('--min-votes', type=int, default=50,
                        help='最小评分人数阈值 (默认: 50)')
    parser.add_argument('--yes', action='store_true',
                        help='跳过确认直接执行')
    parser.add_argument('--dry-run', action='store_true',
                        help='仅查询统计，不执行修改')
    args = parser.parse_args()

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # Step 1: 查询缺失关键数据的电影
    query = '''
        SELECT douban_id, name, douban_score, douban_votes, cover, storyline
        FROM movies
        WHERE douban_score IS NOT NULL
        AND douban_votes >= %s
        AND (cover IS NULL OR cover = '' OR storyline IS NULL OR storyline = '')
    '''
    cursor.execute(query, (args.min_votes,))
    incomplete = cursor.fetchall()
    count = len(incomplete)

    if count == 0:
        print("✅ 没有发现符合条件的不完整电影记录，无需操作。")
        cursor.close()
        conn.close()
        return

    # 统计细节
    missing_cover = sum(1 for r in incomplete if not r.get('cover'))
    missing_storyline = sum(1 for r in incomplete if not r.get('storyline'))
    missing_both = sum(1 for r in incomplete if not r.get('cover') and not r.get('storyline'))

    print(f"📊 发现 {count:,} 条不完整电影记录 (评分人数 >= {args.min_votes})")
    print(f"   缺少 cover: {missing_cover:,}")
    print(f"   缺少 storyline: {missing_storyline:,}")
    print(f"   两者都缺: {missing_both:,}")
    print()

    # 展示示例
    print("   示例:")
    for r in incomplete[:5]:
        cover_status = "✅" if r.get('cover') else "❌"
        story_status = "✅" if r.get('storyline') else "❌"
        print(f"     {r['douban_id']} - {r['name']} "
              f"(⭐{r['douban_score']}, 👥{r['douban_votes']:,}) "
              f"cover:{cover_status} storyline:{story_status}")
    if count > 5:
        print(f"     ... 还有 {count - 5:,} 条")

    if args.dry_run:
        print("\n🔍 仅查询模式 (--dry-run)，不执行修改。")
        cursor.close()
        conn.close()
        return

    # 确认操作
    if not args.yes:
        confirm = input(f"\n⚠️  即将删除这 {count:,} 条不完整记录并重置爬取状态，使爬虫可以重新爬取。继续？(y/n): ")
        if confirm.lower() != 'y':
            print("❌ 操作已取消")
            cursor.close()
            conn.close()
            return

    douban_ids = [r['douban_id'] for r in incomplete]
    batch_size = 500

    # Step 2: 将 subjects 表中对应记录的 crawl_status 重置为 0
    reset_count = 0
    for i in range(0, len(douban_ids), batch_size):
        batch = douban_ids[i:i + batch_size]
        placeholders = ','.join(['%s'] * len(batch))
        cursor.execute(
            f"UPDATE subjects SET crawl_status = 0, crawl_locked_at = NULL, crawl_worker = NULL "
            f"WHERE douban_id IN ({placeholders})",
            batch
        )
        reset_count += cursor.rowcount
    conn.commit()
    print(f"✅ subjects: 已重置 {reset_count:,} 条记录的 crawl_status 为 0")

    # Step 3: 删除 movies 表中的不完整记录
    delete_count = 0
    for i in range(0, len(douban_ids), batch_size):
        batch = douban_ids[i:i + batch_size]
        placeholders = ','.join(['%s'] * len(batch))
        cursor.execute(
            f"DELETE FROM movies WHERE douban_id IN ({placeholders})",
            batch
        )
        delete_count += cursor.rowcount
    conn.commit()
    print(f"✅ movies: 已删除 {delete_count:,} 条不完整记录")

    # Step 4: 验证
    cursor.execute("SELECT COUNT(*) AS cnt FROM movies")
    remaining_movies = cursor.fetchone()['cnt']
    cursor.execute("SELECT COUNT(*) AS cnt FROM subjects WHERE type = 'movie' AND crawl_status = 0")
    pending = cursor.fetchone()['cnt']

    print(f"\n📊 操作完成:")
    print(f"   movies 表剩余记录: {remaining_movies:,}")
    print(f"   subjects 待爬取: {pending:,}")
    print(f"\n🚀 现在可以运行爬虫重新爬取这些电影数据了")
    print(f"   命令: uv run python db-spiders/proxy_crawler.py --direct --update")

    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
