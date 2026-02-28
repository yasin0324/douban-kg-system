#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重爬不完整影人数据

找出 person 表中只有 id 和 name、其他关键字段全为空的记录，
将对应的 person_obj.status 重置为 0，以便 crawl_person.py 重新爬取。

同时临时删除 person 表中的这些不完整记录，这样 fetch_open_person_tasks()
的 LEFT JOIN ... WHERE p.person_id IS NULL 条件就能选中它们。

使用方法:
    1. 先运行此脚本：uv run python db-spiders/recrawl_incomplete_persons.py
    2. 再运行爬虫：uv run python db-spiders/crawl_person.py
"""

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
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # Step 1: 找出不完整记录
    cursor.execute('''
        SELECT person_id, name FROM person 
        WHERE (sex IS NULL OR sex = '') 
        AND (birthplace IS NULL OR birthplace = '') 
        AND (profession IS NULL OR profession = '') 
        AND (biography IS NULL OR biography = '')
    ''')
    incomplete = cursor.fetchall()
    count = len(incomplete)

    if count == 0:
        print("✅ 没有发现不完整的影人记录，无需操作。")
        cursor.close()
        conn.close()
        return

    print(f"📊 发现 {count:,} 条不完整影人记录")
    print(f"   示例: {incomplete[0]['person_id']} - {incomplete[0]['name']}")
    print(f"   示例: {incomplete[1]['person_id']} - {incomplete[1]['name']}")
    print(f"   ...")
    
    # 确认操作
    if '--yes' not in sys.argv:
        confirm = input(f"\n⚠️  即将重置这 {count:,} 条记录，使爬虫可以重新爬取。继续？(y/n): ")
        if confirm.lower() != 'y':
            print("❌ 操作已取消")
            cursor.close()
            conn.close()
            return

    person_ids = [r['person_id'] for r in incomplete]

    # Step 2: 在 person_obj 中将这些记录的 status 重置为 0
    batch_size = 500
    reset_count = 0
    for i in range(0, len(person_ids), batch_size):
        batch = person_ids[i:i + batch_size]
        placeholders = ','.join(['%s'] * len(batch))
        cursor.execute(
            f"UPDATE person_obj SET status = 0 WHERE person_id IN ({placeholders})",
            batch
        )
        reset_count += cursor.rowcount
    conn.commit()
    print(f"✅ person_obj: 已重置 {reset_count:,} 条记录的 status 为 0")

    # Step 3: 删除 person 表中的不完整记录
    # 这样 fetch_open_person_tasks() 的 LEFT JOIN 条件就能选中它们
    delete_count = 0
    for i in range(0, len(person_ids), batch_size):
        batch = person_ids[i:i + batch_size]
        placeholders = ','.join(['%s'] * len(batch))
        cursor.execute(
            f"DELETE FROM person WHERE person_id IN ({placeholders})",
            batch
        )
        delete_count += cursor.rowcount
    conn.commit()
    print(f"✅ person: 已删除 {delete_count:,} 条不完整记录")

    # Step 4: 验证
    cursor.execute("SELECT COUNT(*) AS cnt FROM person")
    remaining = cursor.fetchone()['cnt']
    cursor.execute("SELECT COUNT(*) AS cnt FROM person_obj WHERE status = 0")
    pending = cursor.fetchone()['cnt']

    print(f"\n📊 操作完成:")
    print(f"   person 表剩余记录: {remaining:,}")
    print(f"   person_obj 待爬取: {pending:,}")
    print(f"\n🚀 现在可以运行 crawl_person.py 重新爬取这些影人数据了")
    print(f"   命令: uv run python db-spiders/crawl_person.py")

    cursor.close()
    conn.close()

if __name__ == '__main__':
    main()
