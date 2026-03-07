#!/usr/bin/env python3
"""
回填历史 mock 用户的 is_mock 标记到 MySQL 与 Neo4j。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.mysql import close_pool, get_connection, init_pool
from app.db.neo4j import Neo4jConnection


def fetch_mock_user_rows(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, username FROM users "
            "WHERE is_mock = 0 AND (password_hash = %s OR username LIKE %s OR nickname LIKE %s) "
            "ORDER BY id ASC",
            ("mock_hash", "MockUser_%", "MockUser_%"),
        )
        return cursor.fetchall()


def update_mysql_flags(conn, user_ids):
    placeholders = ", ".join(["%s"] * len(user_ids))
    with conn.cursor() as cursor:
        cursor.execute(
            f"UPDATE users SET is_mock = 1 WHERE id IN ({placeholders})",
            user_ids,
        )
    conn.commit()


def update_neo4j_flags(user_ids):
    driver = Neo4jConnection.get_driver()
    with driver.session() as session:
        record = session.run(
            """
            UNWIND $user_ids AS uid
            MATCH (u:User {id: uid})
            SET u.is_mock = true
            RETURN count(u) AS updated_nodes
            """,
            user_ids=user_ids,
        ).single()
        return int(record["updated_nodes"] if record else 0)


def main():
    init_pool()
    conn = get_connection()
    try:
        rows = fetch_mock_user_rows(conn)
        if not rows:
            print("未发现需要回填的 mock 用户。")
            return

        user_ids = [row["id"] for row in rows]
        update_mysql_flags(conn, user_ids)
        neo4j_count = update_neo4j_flags(user_ids)
        print(f"MySQL 已回填 {len(user_ids)} 个 mock 用户，Neo4j 已更新 {neo4j_count} 个 User 节点。")
    finally:
        conn.close()
        close_pool()
        Neo4jConnection.close()


if __name__ == "__main__":
    main()
