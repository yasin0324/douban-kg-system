#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据质量分析脚本
连接 MySQL 数据库，统计 movies 和 persons 表的数据质量情况，
生成数据质量报告。
"""

import os
import sys
from datetime import datetime
from collections import Counter

import pymysql
from dotenv import load_dotenv

# Load .env from db-spiders
SPIDERS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db-spiders')
load_dotenv(os.path.join(SPIDERS_DIR, '.env'))

# Database config
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


def analyze_movies(cursor):
    """分析 movies 表数据质量"""
    print("\n" + "=" * 60)
    print("📊 Movies 表数据质量分析")
    print("=" * 60)

    # 总记录数
    cursor.execute("SELECT COUNT(*) AS cnt FROM movies")
    total = cursor.fetchone()['cnt']
    print(f"\n📌 总记录数: {total:,}")

    if total == 0:
        print("⚠️  movies 表为空，跳过分析")
        return {'total': 0}

    # 各字段缺失率
    fields = [
        'name', 'type', 'year', 'genres', 'regions', 'languages',
        'douban_score', 'douban_votes', 'release_date',
        'directors', 'actors', 'director_ids', 'actor_ids',
        'cover', 'storyline', 'alias', 'mins', 'imdb_id', 'official_site'
    ]

    print("\n📋 字段缺失率:")
    print(f"  {'字段名':<20} {'非空数':>10} {'缺失数':>10} {'缺失率':>10}")
    print("  " + "-" * 55)

    field_stats = {}
    for field in fields:
        try:
            cursor.execute(
                f"SELECT COUNT(*) AS cnt FROM movies WHERE `{field}` IS NOT NULL AND `{field}` != ''"
            )
            non_null = cursor.fetchone()['cnt']
            missing = total - non_null
            rate = missing / total * 100
            field_stats[field] = {'non_null': non_null, 'missing': missing, 'rate': rate}
            emoji = "✅" if rate < 5 else "⚠️" if rate < 20 else "❌"
            print(f"  {emoji} {field:<18} {non_null:>10,} {missing:>10,} {rate:>9.2f}%")
        except Exception as e:
            print(f"  ❓ {field:<18} (字段不存在或查询出错: {e})")

    # 评分分布
    print("\n📈 评分分布:")
    cursor.execute("""
        SELECT 
            CASE 
                WHEN douban_score IS NULL OR douban_score = 0 THEN '无评分'
                WHEN douban_score < 3 THEN '1-3分'
                WHEN douban_score < 5 THEN '3-5分'
                WHEN douban_score < 7 THEN '5-7分'
                WHEN douban_score < 8 THEN '7-8分'
                WHEN douban_score < 9 THEN '8-9分'
                ELSE '9-10分'
            END AS score_range,
            COUNT(*) AS cnt
        FROM movies
        GROUP BY score_range
        ORDER BY score_range
    """)
    for row in cursor.fetchall():
        bar = "█" * (row['cnt'] * 40 // total)
        print(f"  {row['score_range']:<10} {row['cnt']:>8,} ({row['cnt']/total*100:5.1f}%) {bar}")

    # 异常评分
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM movies WHERE douban_score IS NOT NULL AND (douban_score < 0 OR douban_score > 10)"
    )
    abnormal_scores = cursor.fetchone()['cnt']
    print(f"\n  ⚠️ 评分异常值 (超出0-10范围): {abnormal_scores:,}")

    # 类型分布 (Top 20)
    print("\n🎬 电影类型分布 (Top 20):")
    cursor.execute("SELECT genres FROM movies WHERE genres IS NOT NULL AND genres != ''")
    genre_counter = Counter()
    for row in cursor.fetchall():
        for genre in row['genres'].split('/'):
            genre = genre.strip()
            if genre:
                genre_counter[genre] += 1

    for genre, count in genre_counter.most_common(20):
        bar = "█" * (count * 30 // genre_counter.most_common(1)[0][1])
        print(f"  {genre:<12} {count:>8,} {bar}")
    print(f"  共 {len(genre_counter)} 种类型")

    # 年份分布 (按年代)
    print("\n📅 年代分布:")
    cursor.execute("""
        SELECT 
            CASE
                WHEN year IS NULL THEN '未知'
                WHEN year < 1960 THEN '1960年前'
                WHEN year < 1980 THEN '1960-1979'
                WHEN year < 2000 THEN '1980-1999'
                WHEN year < 2010 THEN '2000-2009'
                WHEN year < 2020 THEN '2010-2019'
                ELSE '2020年后'
            END AS decade,
            COUNT(*) AS cnt
        FROM movies
        GROUP BY decade
        ORDER BY decade
    """)
    for row in cursor.fetchall():
        bar = "█" * (row['cnt'] * 30 // total)
        print(f"  {row['decade']:<12} {row['cnt']:>8,} ({row['cnt']/total*100:5.1f}%) {bar}")

    # 类型分布 (movie vs tv)
    print("\n🎬 内容类型分布 (movie/tv):")
    cursor.execute("""
        SELECT 
            CASE WHEN type = '' OR type IS NULL THEN 'unknown' ELSE type END AS content_type,
            COUNT(*) AS cnt
        FROM movies
        GROUP BY content_type
    """)
    for row in cursor.fetchall():
        print(f"  {row['content_type']:<10} {row['cnt']:>8,} ({row['cnt']/total*100:5.1f}%)")

    # 地区分布 (Top 15)
    print("\n🌍 制片地区分布 (Top 15):")
    cursor.execute("SELECT regions FROM movies WHERE regions IS NOT NULL AND regions != ''")
    region_counter = Counter()
    for row in cursor.fetchall():
        for region in row['regions'].replace('/', ' ').replace(',', ' ').split():
            region = region.strip()
            if region:
                region_counter[region] += 1
    for region, count in region_counter.most_common(15):
        print(f"  {region:<15} {count:>8,}")

    return {
        'total': total,
        'field_stats': field_stats,
        'genre_count': len(genre_counter),
        'abnormal_scores': abnormal_scores,
    }


def analyze_persons(cursor):
    """分析 persons 表数据质量"""
    print("\n" + "=" * 60)
    print("📊 Persons 表数据质量分析")
    print("=" * 60)

    cursor.execute("SELECT COUNT(*) AS cnt FROM person")
    total = cursor.fetchone()['cnt']
    print(f"\n📌 总记录数: {total:,}")

    if total == 0:
        print("⚠️  person 表为空，跳过分析")
        return {'total': 0}

    # 字段缺失率
    fields = ['name', 'sex', 'name_en', 'name_zh', 'birth', 'death', 'birthplace', 'profession', 'biography']

    print("\n📋 字段缺失率:")
    print(f"  {'字段名':<20} {'非空数':>10} {'缺失数':>10} {'缺失率':>10}")
    print("  " + "-" * 55)

    field_stats = {}
    for field in fields:
        try:
            cursor.execute(
                f"SELECT COUNT(*) AS cnt FROM person WHERE `{field}` IS NOT NULL AND `{field}` != ''"
            )
            non_null = cursor.fetchone()['cnt']
            missing = total - non_null
            rate = missing / total * 100
            field_stats[field] = {'non_null': non_null, 'missing': missing, 'rate': rate}
            emoji = "✅" if rate < 5 else "⚠️" if rate < 30 else "❌"
            print(f"  {emoji} {field:<18} {non_null:>10,} {missing:>10,} {rate:>9.2f}%")
        except Exception as e:
            print(f"  ❓ {field:<18} (字段不存在或查询出错: {e})")

    # 性别分布
    print("\n👤 性别分布:")
    cursor.execute("""
        SELECT 
            CASE WHEN sex IS NULL OR sex = '' THEN '未知' ELSE sex END AS gender,
            COUNT(*) AS cnt
        FROM person
        GROUP BY gender
        ORDER BY cnt DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row['gender']:<10} {row['cnt']:>8,} ({row['cnt']/total*100:5.1f}%)")

    # 职业分布
    print("\n💼 职业分布 (Top 15):")
    cursor.execute("SELECT profession FROM person WHERE profession IS NOT NULL AND profession != ''")
    prof_counter = Counter()
    for row in cursor.fetchall():
        for prof in row['profession'].replace('/', ' ').replace(',', ' ').replace('、', ' ').split():
            prof = prof.strip()
            if prof:
                prof_counter[prof] += 1
    for prof, count in prof_counter.most_common(15):
        print(f"  {prof:<15} {count:>8,}")

    return {
        'total': total,
        'field_stats': field_stats,
    }


def analyze_data_linkage(cursor):
    """分析 movies 和 person 之间的数据关联性"""
    print("\n" + "=" * 60)
    print("🔗 数据关联性分析")
    print("=" * 60)

    # movies 中有 actor_ids 的记录数
    cursor.execute("SELECT COUNT(*) AS cnt FROM movies WHERE actor_ids IS NOT NULL AND actor_ids != ''")
    movies_with_actors = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) AS cnt FROM movies WHERE director_ids IS NOT NULL AND director_ids != ''")
    movies_with_directors = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) AS cnt FROM movies")
    total_movies = cursor.fetchone()['cnt']

    print(f"\n  有演员ID的电影: {movies_with_actors:,} / {total_movies:,} ({movies_with_actors/total_movies*100:.1f}%)")
    print(f"  有导演ID的电影: {movies_with_directors:,} / {total_movies:,} ({movies_with_directors/total_movies*100:.1f}%)")

    # 提取所有 person_id，检查在 person 表中的覆盖率
    print("\n  正在统计影人ID覆盖率...")

    # 从 actor_ids 提取所有不重复的 person_id
    cursor.execute("SELECT actor_ids FROM movies WHERE actor_ids IS NOT NULL AND actor_ids != ''")
    all_person_ids = set()
    for row in cursor.fetchall():
        for item in row['actor_ids'].split('|'):
            item = item.strip()
            if ':' in item:
                pid = item.split(':')[-1]
                if pid:
                    all_person_ids.add(pid)

    cursor.execute("SELECT director_ids FROM movies WHERE director_ids IS NOT NULL AND director_ids != ''")
    director_pids = set()
    for row in cursor.fetchall():
        for item in row['director_ids'].split('|'):
            item = item.strip()
            if ':' in item:
                pid = item.split(':')[-1]
                if pid:
                    all_person_ids.add(pid)
                    director_pids.add(pid)

    print(f"  从 movies 表提取的不重复影人ID: {len(all_person_ids):,}")
    print(f"    其中导演ID: {len(director_pids):,}")
    print(f"    其中演员ID: {len(all_person_ids - director_pids):,} (仅演员)")

    # 在 person 表中的覆盖率
    cursor.execute("SELECT COUNT(*) AS cnt FROM person")
    total_person = cursor.fetchone()['cnt']
    print(f"  person 表总记录数: {total_person:,}")

    # 抽样检查匹配率 (全量可能比较慢)
    sample_ids = list(all_person_ids)[:5000]
    if sample_ids:
        placeholders = ','.join(['%s'] * len(sample_ids))
        cursor.execute(
            f"SELECT COUNT(*) AS cnt FROM person WHERE person_id IN ({placeholders})",
            sample_ids
        )
        matched = cursor.fetchone()['cnt']
        match_rate = matched / len(sample_ids) * 100
        print(f"  影人ID匹配率 (抽样{len(sample_ids)}): {matched:,} / {len(sample_ids):,} ({match_rate:.1f}%)")

    # 估算图谱规模
    print(f"\n📊 预估知识图谱规模:")
    print(f"  Movie 节点: ~{total_movies:,}")
    print(f"  Person 节点: ~{len(all_person_ids):,}")

    cursor.execute("SELECT COUNT(DISTINCT genres) FROM movies WHERE genres IS NOT NULL AND genres != ''")
    # 统计所有类型
    cursor.execute("SELECT genres FROM movies WHERE genres IS NOT NULL AND genres != ''")
    all_genres = set()
    for row in cursor.fetchall():
        for g in row['genres'].split('/'):
            g = g.strip()
            if g:
                all_genres.add(g)
    print(f"  Genre 节点: ~{len(all_genres)}")

    # 估算关系数
    cursor.execute("SELECT SUM(LENGTH(actor_ids) - LENGTH(REPLACE(actor_ids, '|', '')) + 1) AS cnt FROM movies WHERE actor_ids IS NOT NULL AND actor_ids != ''")
    act_rels = cursor.fetchone()['cnt'] or 0
    cursor.execute("SELECT SUM(LENGTH(director_ids) - LENGTH(REPLACE(director_ids, '|', '')) + 1) AS cnt FROM movies WHERE director_ids IS NOT NULL AND director_ids != ''")
    dir_rels = cursor.fetchone()['cnt'] or 0
    cursor.execute("SELECT SUM(LENGTH(genres) - LENGTH(REPLACE(genres, '/', '')) + 1) AS cnt FROM movies WHERE genres IS NOT NULL AND genres != ''")
    genre_rels = cursor.fetchone()['cnt'] or 0

    print(f"  ACTED_IN 关系: ~{int(act_rels):,}")
    print(f"  DIRECTED 关系: ~{int(dir_rels):,}")
    print(f"  HAS_GENRE 关系: ~{int(genre_rels):,}")
    print(f"  总关系数: ~{int(act_rels + dir_rels + genre_rels):,}")

    return {
        'unique_person_ids': len(all_person_ids),
        'genres': len(all_genres),
        'est_acted_in': int(act_rels),
        'est_directed': int(dir_rels),
        'est_has_genre': int(genre_rels),
    }


def generate_report(movie_stats, person_stats, linkage_stats):
    """生成 Markdown 格式的数据质量报告"""
    report_dir = os.path.join(os.path.dirname(__file__), 'reports')
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, 'data_quality_report.md')

    lines = [
        f"# 数据质量报告",
        f"",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"## 1. 数据规模概览",
        f"",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| Movies 表记录数 | {movie_stats.get('total', 0):,} |",
        f"| Persons 表记录数 | {person_stats.get('total', 0):,} |",
        f"| 不重复影人ID数 | {linkage_stats.get('unique_person_ids', 0):,} |",
        f"| 电影类型数 | {linkage_stats.get('genres', 0)} |",
        f"",
        f"## 2. 预估图谱规模",
        f"",
        f"| 关系类型 | 预估数量 |",
        f"|----------|----------|",
        f"| ACTED_IN | {linkage_stats.get('est_acted_in', 0):,} |",
        f"| DIRECTED | {linkage_stats.get('est_directed', 0):,} |",
        f"| HAS_GENRE | {linkage_stats.get('est_has_genre', 0):,} |",
        f"| **总计** | **{linkage_stats.get('est_acted_in', 0) + linkage_stats.get('est_directed', 0) + linkage_stats.get('est_has_genre', 0):,}** |",
        f"",
    ]

    # Movies 字段缺失率
    if movie_stats.get('field_stats'):
        lines.extend([
            f"## 3. Movies 字段缺失率",
            f"",
            f"| 字段 | 非空数 | 缺失数 | 缺失率 | 状态 |",
            f"|------|--------|--------|--------|------|",
        ])
        for field, stats in movie_stats['field_stats'].items():
            status = "✅" if stats['rate'] < 5 else "⚠️" if stats['rate'] < 20 else "❌"
            lines.append(
                f"| {field} | {stats['non_null']:,} | {stats['missing']:,} | {stats['rate']:.2f}% | {status} |"
            )
        lines.append("")

    # Persons 字段缺失率
    if person_stats.get('field_stats'):
        lines.extend([
            f"## 4. Persons 字段缺失率",
            f"",
            f"| 字段 | 非空数 | 缺失数 | 缺失率 | 状态 |",
            f"|------|--------|--------|--------|------|",
        ])
        for field, stats in person_stats['field_stats'].items():
            status = "✅" if stats['rate'] < 5 else "⚠️" if stats['rate'] < 30 else "❌"
            lines.append(
                f"| {field} | {stats['non_null']:,} | {stats['missing']:,} | {stats['rate']:.2f}% | {status} |"
            )
        lines.append("")

    report_content = '\n'.join(lines)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
    print(f"\n📄 报告已保存到: {report_path}")
    return report_path


def main():
    print("🚀 开始数据质量分析...")
    print(f"   数据库: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['db']}")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        movie_stats = analyze_movies(cursor)
        person_stats = analyze_persons(cursor)
        linkage_stats = analyze_data_linkage(cursor)
        report_path = generate_report(movie_stats, person_stats, linkage_stats)

        print("\n" + "=" * 60)
        print("✅ 数据质量分析完成！")
        print("=" * 60)
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    main()
