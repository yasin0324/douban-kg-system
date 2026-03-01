#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ETL 脚本：从 MySQL 导入数据到 Neo4j 知识图谱

按 schema_design.md 的定义，创建：
- 节点：Movie, Person, Genre
- 关系：DIRECTED, ACTED_IN, HAS_GENRE

使用 UNWIND 批量导入优化性能。
"""

import os
import sys
import pymysql
from dotenv import load_dotenv
from neo4j import GraphDatabase
from tqdm import tqdm

SPIDERS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db-spiders')
load_dotenv(os.path.join(SPIDERS_DIR, '.env'))

# MySQL config
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '3306')),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASS', '1224guoyuanxin'),
    'db': os.environ.get('DB_NAME', 'douban'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,
}

# Neo4j config
NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
NEO4J_PASS = os.environ.get('NEO4J_PASS', 'douban2026')

BATCH_SIZE = 2000  # batch size for UNWIND operations


def get_mysql_connection():
    return pymysql.connect(**DB_CONFIG)


def get_neo4j_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))


# ============== Phase 1: Constraints & Indexes ==============

def create_constraints(driver):
    """创建唯一性约束和索引"""
    print("\n📐 Phase 1: 创建约束和索引...")

    queries = [
        "CREATE CONSTRAINT movie_mid IF NOT EXISTS FOR (m:Movie) REQUIRE m.mid IS UNIQUE",
        "CREATE CONSTRAINT person_pid IF NOT EXISTS FOR (p:Person) REQUIRE p.pid IS UNIQUE",
        "CREATE CONSTRAINT genre_name IF NOT EXISTS FOR (g:Genre) REQUIRE g.name IS UNIQUE",
        "CREATE INDEX movie_title IF NOT EXISTS FOR (m:Movie) ON (m.title)",
        "CREATE INDEX movie_rating IF NOT EXISTS FOR (m:Movie) ON (m.rating)",
        "CREATE INDEX person_name IF NOT EXISTS FOR (p:Person) ON (p.name)",
    ]

    with driver.session() as session:
        for q in queries:
            try:
                session.run(q)
                print(f"  ✅ {q[:60]}...")
            except Exception as e:
                print(f"  ⚠️ {q[:60]}... ({e})")

    print("  ✅ 约束和索引创建完成")


# ============== Phase 2: Genre Nodes ==============

def import_genres(driver, mysql_cursor):
    """导入 Genre 节点"""
    print("\n🏷️  Phase 2: 导入 Genre 节点...")

    mysql_cursor.execute("SELECT genres FROM movies WHERE genres IS NOT NULL")
    all_genres = set()
    for row in mysql_cursor.fetchall():
        for g in row['genres'].split('/'):
            g = g.strip()
            if g:
                all_genres.add(g)

    genre_list = [{'name': g} for g in sorted(all_genres)]

    with driver.session() as session:
        session.run(
            "UNWIND $genres AS g MERGE (genre:Genre {name: g.name})",
            genres=genre_list
        )

    print(f"  ✅ 导入 {len(genre_list)} 个 Genre 节点")
    return len(genre_list)


# ============== Phase 3: Movie Nodes ==============

def import_movies(driver, mysql_cursor):
    """导入 Movie 节点"""
    print("\n🎬 Phase 3: 导入 Movie 节点...")

    mysql_cursor.execute("SELECT COUNT(*) AS cnt FROM movies")
    total = mysql_cursor.fetchone()['cnt']

    mysql_cursor.execute("""
        SELECT douban_id, name, type, douban_score, douban_votes, release_date, cover, year,
               regions, languages, mins, storyline, alias
        FROM movies
    """)

    imported = 0
    batch = []
    pbar = tqdm(total=total, desc="  Movies", unit="部")

    for row in mysql_cursor:
        movie = {
            'mid': str(row['douban_id']),
            'title': row['name'],
            'content_type': row.get('type', 'movie'),
            'rating': float(row['douban_score']) if row.get('douban_score') else None,
            'votes': int(row['douban_votes']) if row.get('douban_votes') else None,
            'release_date': str(row['release_date']) if row.get('release_date') else None,
            'cover': row.get('cover'),
            'year': row.get('year'),
            'regions': row.get('regions'),
            'languages': row.get('languages'),
            'runtime': row.get('mins'),
            'storyline': row.get('storyline'),
            'alias': row.get('alias'),
            'url': f"https://movie.douban.com/subject/{row['douban_id']}/",
        }
        batch.append(movie)

        if len(batch) >= BATCH_SIZE:
            _insert_movie_batch(driver, batch)
            imported += len(batch)
            pbar.update(len(batch))
            batch = []

    if batch:
        _insert_movie_batch(driver, batch)
        imported += len(batch)
        pbar.update(len(batch))

    pbar.close()
    print(f"  ✅ 导入 {imported:,} 个 Movie 节点")
    return imported


def _insert_movie_batch(driver, batch):
    """批量插入 Movie 节点"""
    cypher = """
    UNWIND $movies AS m
    MERGE (movie:Movie {mid: m.mid})
    SET movie.title = m.title,
        movie.content_type = m.content_type,
        movie.rating = m.rating,
        movie.votes = m.votes,
        movie.release_date = m.release_date,
        movie.cover = m.cover,
        movie.year = m.year,
        movie.regions = m.regions,
        movie.languages = m.languages,
        movie.runtime = m.runtime,
        movie.storyline = m.storyline,
        movie.alias = m.alias,
        movie.url = m.url
    """
    with driver.session() as session:
        session.run(cypher, movies=batch)


# ============== Phase 4: Person Nodes ==============

def import_persons(driver, mysql_cursor):
    """导入 Person 节点"""
    print("\n👤 Phase 4: 导入 Person 节点...")

    mysql_cursor.execute("SELECT COUNT(*) AS cnt FROM person")
    total = mysql_cursor.fetchone()['cnt']

    mysql_cursor.execute("""
        SELECT person_id, name, sex, name_en, name_zh,
               birth, death, birthplace, profession, biography
        FROM person
    """)

    imported = 0
    batch = []
    pbar = tqdm(total=total, desc="  Persons", unit="人")

    for row in mysql_cursor:
        person = {
            'pid': str(row['person_id']),
            'name': row['name'],
            'sex': row.get('sex'),
            'name_en': row.get('name_en'),
            'name_zh': row.get('name_zh'),
            'birth': str(row['birth']) if row.get('birth') else None,
            'death': str(row['death']) if row.get('death') else None,
            'birthplace': row.get('birthplace'),
            'profession': row.get('profession'),
            'biography': row.get('biography'),
        }
        batch.append(person)

        if len(batch) >= BATCH_SIZE:
            _insert_person_batch(driver, batch)
            imported += len(batch)
            pbar.update(len(batch))
            batch = []

    if batch:
        _insert_person_batch(driver, batch)
        imported += len(batch)
        pbar.update(len(batch))

    pbar.close()
    print(f"  ✅ 导入 {imported:,} 个 Person 节点")
    return imported


def _insert_person_batch(driver, batch):
    """批量插入 Person 节点"""
    cypher = """
    UNWIND $persons AS p
    MERGE (person:Person {pid: p.pid})
    SET person.name = p.name,
        person.sex = p.sex,
        person.name_en = p.name_en,
        person.name_zh = p.name_zh,
        person.birth = p.birth,
        person.death = p.death,
        person.birthplace = p.birthplace,
        person.profession = p.profession,
        person.biography = p.biography
    """
    with driver.session() as session:
        session.run(cypher, persons=batch)


# ============== Phase 5: DIRECTED Relationships ==============

def import_directed_relations(driver, mysql_cursor):
    """创建 DIRECTED 关系 (Person)-[:DIRECTED]->(Movie)"""
    print("\n🎬 Phase 5: 创建 DIRECTED 关系...")

    mysql_cursor.execute("""
        SELECT douban_id, director_ids FROM movies
        WHERE director_ids IS NOT NULL
    """)

    total_rels = 0
    batch = []
    rows = mysql_cursor.fetchall()
    pbar = tqdm(total=len(rows), desc="  Directed", unit="部")

    for row in rows:
        mid = str(row['douban_id'])
        for item in row['director_ids'].split('|'):
            item = item.strip()
            if ':' in item:
                parts = item.rsplit(':', 1)
                pid = parts[-1].strip()
                name = parts[0].strip()
                if pid:
                    batch.append({'pid': pid, 'mid': mid, 'name': name})

        pbar.update(1)

        if len(batch) >= BATCH_SIZE:
            _insert_directed_batch(driver, batch)
            total_rels += len(batch)
            batch = []

    if batch:
        _insert_directed_batch(driver, batch)
        total_rels += len(batch)

    pbar.close()
    print(f"  ✅ 创建 {total_rels:,} 条 DIRECTED 关系")
    return total_rels


def _insert_directed_batch(driver, batch):
    """批量创建 DIRECTED 关系"""
    cypher = """
    UNWIND $rels AS r
    MATCH (p:Person {pid: r.pid})
    MATCH (m:Movie {mid: r.mid})
    MERGE (p)-[:DIRECTED]->(m)
    """
    with driver.session() as session:
        session.run(cypher, rels=batch)


# ============== Phase 6: ACTED_IN Relationships ==============

def import_acted_in_relations(driver, mysql_cursor):
    """创建 ACTED_IN 关系 (Person)-[:ACTED_IN]->(Movie)"""
    print("\n🎭 Phase 6: 创建 ACTED_IN 关系...")

    mysql_cursor.execute("""
        SELECT douban_id, actor_ids FROM movies
        WHERE actor_ids IS NOT NULL
    """)

    total_rels = 0
    batch = []
    rows = mysql_cursor.fetchall()
    pbar = tqdm(total=len(rows), desc="  ActedIn", unit="部")

    for row in rows:
        mid = str(row['douban_id'])
        actors = row['actor_ids'].split('|')
        for order, item in enumerate(actors, 1):
            item = item.strip()
            if ':' in item:
                parts = item.rsplit(':', 1)
                pid = parts[-1].strip()
                name = parts[0].strip()
                if pid:
                    batch.append({'pid': pid, 'mid': mid, 'order': order, 'name': name})

        pbar.update(1)

        if len(batch) >= BATCH_SIZE:
            _insert_acted_in_batch(driver, batch)
            total_rels += len(batch)
            batch = []

    if batch:
        _insert_acted_in_batch(driver, batch)
        total_rels += len(batch)

    pbar.close()
    print(f"  ✅ 创建 {total_rels:,} 条 ACTED_IN 关系")
    return total_rels


def _insert_acted_in_batch(driver, batch):
    """批量创建 ACTED_IN 关系"""
    cypher = """
    UNWIND $rels AS r
    MATCH (p:Person {pid: r.pid})
    MATCH (m:Movie {mid: r.mid})
    MERGE (p)-[rel:ACTED_IN]->(m)
    SET rel.order = r.order
    """
    with driver.session() as session:
        session.run(cypher, rels=batch)


# ============== Phase 7: HAS_GENRE Relationships ==============

def import_has_genre_relations(driver, mysql_cursor):
    """创建 HAS_GENRE 关系 (Movie)-[:HAS_GENRE]->(Genre)"""
    print("\n🏷️  Phase 7: 创建 HAS_GENRE 关系...")

    mysql_cursor.execute("""
        SELECT douban_id, genres FROM movies
        WHERE genres IS NOT NULL
    """)

    total_rels = 0
    batch = []
    rows = mysql_cursor.fetchall()
    pbar = tqdm(total=len(rows), desc="  HasGenre", unit="部")

    for row in rows:
        mid = str(row['douban_id'])
        for genre in row['genres'].split('/'):
            genre = genre.strip()
            if genre:
                batch.append({'mid': mid, 'genre': genre})

        pbar.update(1)

        if len(batch) >= BATCH_SIZE:
            _insert_has_genre_batch(driver, batch)
            total_rels += len(batch)
            batch = []

    if batch:
        _insert_has_genre_batch(driver, batch)
        total_rels += len(batch)

    pbar.close()
    print(f"  ✅ 创建 {total_rels:,} 条 HAS_GENRE 关系")
    return total_rels


def _insert_has_genre_batch(driver, batch):
    """批量创建 HAS_GENRE 关系"""
    cypher = """
    UNWIND $rels AS r
    MATCH (m:Movie {mid: r.mid})
    MATCH (g:Genre {name: r.genre})
    MERGE (m)-[:HAS_GENRE]->(g)
    """
    with driver.session() as session:
        session.run(cypher, rels=batch)


# ============== Verification ==============

def verify_import(driver):
    """验证导入结果"""
    print("\n" + "=" * 60)
    print("🔍 验证导入结果")
    print("=" * 60)

    with driver.session() as session:
        # Node counts
        result = session.run("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC")
        print("\n📊 节点统计:")
        for record in result:
            print(f"  {record['label']:<10} {record['count']:>10,}")

        # Relationship counts
        result = session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count ORDER BY count DESC")
        print("\n📊 关系统计:")
        for record in result:
            print(f"  {record['type']:<15} {record['count']:>10,}")

        # Sample query: 肖申克的救赎
        print("\n🎬 示例查询: 搜索 '肖申克的救赎'")
        result = session.run("""
            MATCH (m:Movie)
            WHERE m.title CONTAINS '肖申克'
            OPTIONAL MATCH (d:Person)-[:DIRECTED]->(m)
            OPTIONAL MATCH (a:Person)-[:ACTED_IN]->(m)
            OPTIONAL MATCH (m)-[:HAS_GENRE]->(g:Genre)
            RETURN m.title AS title, m.rating AS rating,
                   collect(DISTINCT d.name) AS directors,
                   collect(DISTINCT a.name)[0..5] AS actors,
                   collect(DISTINCT g.name) AS genres
            LIMIT 3
        """)
        for record in result:
            print(f"  🎬 {record['title']} (评分: {record['rating']})")
            print(f"     导演: {', '.join(record['directors']) if record['directors'] else '未知'}")
            print(f"     演员: {', '.join(record['actors']) if record['actors'] else '未知'}")
            print(f"     类型: {', '.join(record['genres']) if record['genres'] else '未知'}")

        # 关联度最高的演员
        print("\n🌟 参演电影最多的演员 (Top 10):")
        result = session.run("""
            MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
            RETURN p.name AS name, p.pid AS pid, count(m) AS movie_count
            ORDER BY movie_count DESC
            LIMIT 10
        """)
        for record in result:
            print(f"  {record['name']:<20} {record['movie_count']:>5} 部电影")


def main():
    print("🚀 开始 ETL: MySQL → Neo4j")
    print(f"   MySQL: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['db']}")
    print(f"   Neo4j: {NEO4J_URI}")

    # Connect
    mysql_conn = get_mysql_connection()
    mysql_cursor = mysql_conn.cursor()
    neo4j_driver = get_neo4j_driver()

    try:
        # Verify Neo4j connection
        neo4j_driver.verify_connectivity()
        print("   ✅ Neo4j 连接成功")
    except Exception as e:
        print(f"\n❌ 无法连接 Neo4j: {e}")
        print("\n请确保 Neo4j 已启动。可以使用以下命令启动:")
        print("  docker run -d --name neo4j \\")
        print("    -p 7474:7474 -p 7687:7687 \\")
        print("    -e NEO4J_AUTH=neo4j/douban2026 \\")
        print("    -v neo4j_data:/data \\")
        print("    neo4j:5")
        sys.exit(1)

    try:
        create_constraints(neo4j_driver)

        import_genres(neo4j_driver, mysql_cursor)

        # Need new cursor for each large query
        mysql_cursor.close()
        mysql_cursor = mysql_conn.cursor()
        import_movies(neo4j_driver, mysql_cursor)

        mysql_cursor.close()
        mysql_cursor = mysql_conn.cursor()
        import_persons(neo4j_driver, mysql_cursor)

        mysql_cursor.close()
        mysql_cursor = mysql_conn.cursor()
        import_directed_relations(neo4j_driver, mysql_cursor)

        mysql_cursor.close()
        mysql_cursor = mysql_conn.cursor()
        import_acted_in_relations(neo4j_driver, mysql_cursor)

        mysql_cursor.close()
        mysql_cursor = mysql_conn.cursor()
        import_has_genre_relations(neo4j_driver, mysql_cursor)

        verify_import(neo4j_driver)

        print("\n" + "=" * 60)
        print("✅ ETL 完成！知识图谱已构建。")
        print("=" * 60)
        print(f"\n🌐 打开 Neo4j Browser 查看图谱: http://localhost:7474")
        print(f"   用户名: {NEO4J_USER}")
        print(f"   密码: {NEO4J_PASS}")

    finally:
        mysql_cursor.close()
        mysql_conn.close()
        neo4j_driver.close()


if __name__ == '__main__':
    main()
