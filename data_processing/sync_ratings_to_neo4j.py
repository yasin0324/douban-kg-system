#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
将 MySQL 中的用户评分数据同步到 Neo4j 知识图谱

创建:
- User 节点 (uid: 对应 MySQL users.id)
- RATED 关系 (User)-[:RATED {rating: float}]->(Movie)

用法:
    python -m data_processing.sync_ratings_to_neo4j
"""

import os
import sys

import pymysql
from dotenv import load_dotenv
from neo4j import GraphDatabase

SPIDERS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db-spiders")
load_dotenv(os.path.join(SPIDERS_DIR, ".env"))

# MySQL config
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "3306")),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASS", "1224guoyuanxin"),
    "db": os.environ.get("DB_NAME", "douban"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

# Neo4j config
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASS", "douban2026")

BATCH_SIZE = 1000


def create_user_constraints(driver):
    """创建 User 节点的唯一性约束"""
    print("📐 创建 User 约束...")
    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT user_uid IF NOT EXISTS "
            "FOR (u:User) REQUIRE u.uid IS UNIQUE"
        )
    print("  ✅ User 约束创建完成")


def sync_users(driver, mysql_cursor):
    """同步用户节点"""
    print("\n👤 同步 User 节点...")
    mysql_cursor.execute(
        "SELECT DISTINCT u.id, u.username, u.nickname "
        "FROM users u "
        "INNER JOIN user_movie_ratings r ON r.user_id = u.id"
    )
    users = mysql_cursor.fetchall()

    user_list = [
        {
            "uid": str(row["id"]),
            "username": row["username"],
            "nickname": row.get("nickname") or row["username"],
        }
        for row in users
    ]

    if not user_list:
        print("  ⚠️ 没有找到有评分的用户")
        return 0

    with driver.session() as session:
        for i in range(0, len(user_list), BATCH_SIZE):
            batch = user_list[i : i + BATCH_SIZE]
            session.run(
                "UNWIND $users AS u "
                "MERGE (user:User {uid: u.uid}) "
                "SET user.username = u.username, user.nickname = u.nickname",
                users=batch,
            )

    print(f"  ✅ 同步 {len(user_list)} 个 User 节点")
    return len(user_list)


def sync_ratings(driver, mysql_cursor):
    """同步 RATED 关系"""
    print("\n⭐ 同步 RATED 关系...")
    mysql_cursor.execute(
        "SELECT user_id, mid, rating FROM user_movie_ratings"
    )
    ratings = mysql_cursor.fetchall()

    rating_list = [
        {
            "uid": str(row["user_id"]),
            "mid": str(row["mid"]),
            "rating": float(row["rating"]),
        }
        for row in ratings
    ]

    if not rating_list:
        print("  ⚠️ 没有找到评分数据")
        return 0

    with driver.session() as session:
        for i in range(0, len(rating_list), BATCH_SIZE):
            batch = rating_list[i : i + BATCH_SIZE]
            session.run(
                "UNWIND $ratings AS r "
                "MATCH (u:User {uid: r.uid}) "
                "MATCH (m:Movie {mid: r.mid}) "
                "MERGE (u)-[rel:RATED]->(m) "
                "SET rel.rating = r.rating",
                ratings=batch,
            )

    print(f"  ✅ 同步 {len(rating_list)} 条 RATED 关系")
    return len(rating_list)


def verify_sync(driver):
    """验证同步结果"""
    print("\n🔍 验证同步结果:")
    with driver.session() as session:
        result = session.run("MATCH (u:User) RETURN count(u) AS cnt")
        user_count = result.single()["cnt"]
        print(f"  User 节点: {user_count}")

        result = session.run("MATCH ()-[r:RATED]->() RETURN count(r) AS cnt")
        rated_count = result.single()["cnt"]
        print(f"  RATED 关系: {rated_count}")

        result = session.run(
            "MATCH (u:User)-[r:RATED]->(m:Movie) "
            "RETURN u.username AS user, m.title AS movie, r.rating AS rating "
            "LIMIT 5"
        )
        print("\n  示例数据:")
        for record in result:
            print(f"    {record['user']} → {record['movie']} (评分: {record['rating']})")


def main():
    print("🚀 开始同步评分数据到 Neo4j")

    mysql_conn = pymysql.connect(**DB_CONFIG)
    mysql_cursor = mysql_conn.cursor()
    neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    try:
        neo4j_driver.verify_connectivity()
        print("  ✅ Neo4j 连接成功")
    except Exception as e:
        print(f"❌ 无法连接 Neo4j: {e}")
        sys.exit(1)

    try:
        create_user_constraints(neo4j_driver)
        sync_users(neo4j_driver, mysql_cursor)

        mysql_cursor.close()
        mysql_cursor = mysql_conn.cursor()
        sync_ratings(neo4j_driver, mysql_cursor)

        verify_sync(neo4j_driver)
        print("\n✅ 同步完成！")
    finally:
        mysql_cursor.close()
        mysql_conn.close()
        neo4j_driver.close()


if __name__ == "__main__":
    main()
