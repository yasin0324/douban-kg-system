"""
Clean up legacy recommendation users in MySQL.

Actions:
1. Delete historical mock users whose username matches `seed_cfkg_%`.
2. Mark imported public Douban users `douban_public_%` as real users (`is_mock = 0`).
"""
from __future__ import annotations

import argparse
import json

from app.db.mysql import close_pool, get_connection, init_pool

SEED_PREFIX = "seed_cfkg_%"
PUBLIC_PREFIX = "douban_public_%"


def table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES LIKE %s", (table_name,))
        return cursor.fetchone() is not None


def count_rows(conn, sql: str, params: tuple = ()) -> int:
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    return int(row["cnt"]) if row else 0


def summarize(conn) -> dict[str, int]:
    return {
        "seed_users": count_rows(conn, "SELECT COUNT(*) AS cnt FROM users WHERE username LIKE %s", (SEED_PREFIX,)),
        "seed_ratings": count_rows(
            conn,
            "SELECT COUNT(*) AS cnt FROM user_movie_ratings r JOIN users u ON u.id = r.user_id WHERE u.username LIKE %s",
            (SEED_PREFIX,),
        ),
        "seed_prefs": count_rows(
            conn,
            "SELECT COUNT(*) AS cnt FROM user_movie_prefs p JOIN users u ON u.id = p.user_id WHERE u.username LIKE %s",
            (SEED_PREFIX,),
        ),
        "public_users": count_rows(conn, "SELECT COUNT(*) AS cnt FROM users WHERE username LIKE %s", (PUBLIC_PREFIX,)),
        "public_mock_users": count_rows(
            conn,
            "SELECT COUNT(*) AS cnt FROM users WHERE username LIKE %s AND is_mock = 1",
            (PUBLIC_PREFIX,),
        ),
        "public_ratings": count_rows(
            conn,
            "SELECT COUNT(*) AS cnt FROM user_movie_ratings r JOIN users u ON u.id = r.user_id WHERE u.username LIKE %s",
            (PUBLIC_PREFIX,),
        ),
        "public_prefs": count_rows(
            conn,
            "SELECT COUNT(*) AS cnt FROM user_movie_prefs p JOIN users u ON u.id = p.user_id WHERE u.username LIKE %s",
            (PUBLIC_PREFIX,),
        ),
    }


def delete_rows_by_user_prefix(conn, table_name: str, prefix: str, *, user_column: str = "user_id") -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            f"DELETE target FROM {table_name} target "
            f"JOIN users u ON u.id = target.{user_column} "
            "WHERE u.username LIKE %s",
            (prefix,),
        )
        affected = cursor.rowcount
    conn.commit()
    return int(affected)


def delete_seed_cfkg_users(conn) -> dict[str, int]:
    deleted = {}
    if table_exists(conn, "admin_user_actions"):
        deleted["admin_user_actions"] = delete_rows_by_user_prefix(
            conn,
            "admin_user_actions",
            SEED_PREFIX,
            user_column="target_user_id",
        )
    if table_exists(conn, "user_search_history"):
        deleted["user_search_history"] = delete_rows_by_user_prefix(conn, "user_search_history", SEED_PREFIX)
    if table_exists(conn, "user_sessions"):
        deleted["user_sessions"] = delete_rows_by_user_prefix(conn, "user_sessions", SEED_PREFIX)
    if table_exists(conn, "user_movie_prefs"):
        deleted["user_movie_prefs"] = delete_rows_by_user_prefix(conn, "user_movie_prefs", SEED_PREFIX)
    if table_exists(conn, "user_movie_ratings"):
        deleted["user_movie_ratings"] = delete_rows_by_user_prefix(conn, "user_movie_ratings", SEED_PREFIX)

    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM users WHERE username LIKE %s", (SEED_PREFIX,))
        deleted["users"] = int(cursor.rowcount)
    conn.commit()
    return deleted


def mark_public_users_real(conn) -> int:
    if not table_exists(conn, "users"):
        return 0
    with conn.cursor() as cursor:
        cursor.execute(
            "UPDATE users SET is_mock = 0, updated_at = NOW() WHERE username LIKE %s AND is_mock <> 0",
            (PUBLIC_PREFIX,),
        )
        affected = cursor.rowcount
    conn.commit()
    return int(affected)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean up legacy recommendation users.")
    parser.add_argument("--dry-run", action="store_true", help="Show before/after plan without mutating the database.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    init_pool()
    conn = get_connection()
    try:
        before = summarize(conn)
        if args.dry_run:
            print(json.dumps({"mode": "dry-run", "before": before}, ensure_ascii=False, indent=2))
            return 0

        deleted = delete_seed_cfkg_users(conn)
        public_updated = mark_public_users_real(conn)
        after = summarize(conn)
        print(
            json.dumps(
                {
                    "deleted": deleted,
                    "public_updated": public_updated,
                    "before": before,
                    "after": after,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        conn.close()
        close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
