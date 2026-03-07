#!/usr/bin/env python3
"""
写入一批用于离线评估的“伪真实用户”及评分数据。

这些用户会保留 `eval_real_` 前缀，便于后续定位和清理；
但 `is_mock = 0`，从而会进入离线评估脚本的真实用户分层。
"""
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.mysql import close_pool, get_connection, init_pool
from app.db.neo4j import Neo4jConnection
from app.services.auth_service import hash_password

RANDOM_SEED = 20260307
USERS_PER_PERSONA = 3
START_DATE = datetime(2024, 1, 1, 12, 0, 0)
PASSWORD = "eval-real-pass"

PERSONAS = [
    {"slug": "scifi", "label": "科幻悬疑迷", "preferred": ["科幻", "悬疑"], "avoid": ["家庭", "儿童", "纪录片"]},
    {"slug": "arthouse", "label": "剧情爱情派", "preferred": ["剧情", "爱情"], "avoid": ["动作", "恐怖", "儿童"]},
    {"slug": "action", "label": "动作犯罪控", "preferred": ["动作", "犯罪"], "avoid": ["爱情", "家庭", "儿童"]},
    {"slug": "animation", "label": "动画奇幻党", "preferred": ["动画", "奇幻"], "avoid": ["纪录片", "战争", "真人秀"]},
    {"slug": "comedy", "label": "喜剧治愈派", "preferred": ["喜剧", "家庭"], "avoid": ["恐怖", "惊悚", "战争"]},
    {"slug": "history", "label": "纪录历史控", "preferred": ["纪录片", "历史"], "avoid": ["儿童", "动画", "奇幻"]},
]


def split_genres(genres: str):
    return [part.strip() for part in (genres or "").split("/") if part.strip()]


def load_movie_pool(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT douban_id, name, genres, douban_score, douban_votes, year
            FROM movies
            WHERE type = 'movie'
              AND genres IS NOT NULL AND genres != ''
              AND douban_score IS NOT NULL
              AND douban_votes IS NOT NULL
            ORDER BY douban_votes DESC, douban_score DESC
            LIMIT 60000
            """
        )
        rows = cursor.fetchall()

    movies = []
    for row in rows:
        movie = dict(row)
        movie["douban_id"] = str(movie["douban_id"])
        movie["genre_list"] = split_genres(movie["genres"])
        movie["douban_score"] = float(movie["douban_score"])
        movie["douban_votes"] = int(movie["douban_votes"])
        movies.append(movie)
    return movies


def take_unique(pool, count, used_ids, offset=0):
    selected = []
    total = len(pool)
    if total == 0:
        return selected

    for index in range(total):
        movie = pool[(offset + index) % total]
        movie_id = movie["douban_id"]
        if movie_id in used_ids:
            continue
        used_ids.add(movie_id)
        selected.append(movie)
        if len(selected) >= count:
            break
    return selected


def build_persona_pool(movies, persona):
    preferred = []
    secondary = []
    disliked = []
    neutral = []

    for movie in movies:
        genres = movie["genre_list"]
        matched_preferred = any(keyword in genres for keyword in persona["preferred"])
        matched_avoid = any(keyword in genres for keyword in persona["avoid"])
        if matched_preferred and movie["douban_score"] >= 7.0:
            preferred.append(movie)
        elif matched_preferred:
            secondary.append(movie)
        elif matched_avoid:
            disliked.append(movie)
        else:
            neutral.append(movie)

    preferred = preferred or secondary
    if len(preferred) < 20:
        preferred = (preferred + neutral)[:20]
    if len(neutral) < 12:
        neutral = neutral + preferred
    if len(disliked) < 8:
        disliked = disliked + neutral

    return {
        "preferred": preferred,
        "neutral": neutral,
        "disliked": disliked,
    }


def build_rating_plan(persona_pool, user_index: int):
    used_ids = set()
    shared_core = persona_pool["preferred"][:12]
    holdout = shared_core[(user_index * 2) % len(shared_core)]
    used_ids.add(holdout["douban_id"])

    history_high = take_unique(shared_core, 5, used_ids, offset=user_index)
    extra_high = take_unique(persona_pool["preferred"], 3, used_ids, offset=12 + user_index * 5)
    neutral = take_unique(persona_pool["neutral"], 4, used_ids, offset=user_index * 7)
    disliked = take_unique(persona_pool["disliked"], 3, used_ids, offset=user_index * 9)

    history_items = []
    for movie in history_high[:3]:
        history_items.append((movie, 5.0))
    for movie in neutral[:2]:
        history_items.append((movie, 3.5))
    for movie in extra_high[:2]:
        history_items.append((movie, 4.5))
    for movie in disliked[:2]:
        history_items.append((movie, 2.0))
    for movie in history_high[3:]:
        history_items.append((movie, 4.5))
    for movie in neutral[2:]:
        history_items.append((movie, 3.0))
    for movie in disliked[2:]:
        history_items.append((movie, 1.5))
    for movie in extra_high[2:]:
        history_items.append((movie, 4.0))

    history_items.append((holdout, 5.0))
    return history_items


def upsert_eval_user(conn, username: str, nickname: str):
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE users SET nickname = %s, is_mock = 0, status = 'active' WHERE id = %s",
                (nickname, row["id"]),
            )
            user_id = row["id"]
        else:
            cursor.execute(
                "INSERT INTO users (username, password_hash, nickname, status, is_mock) VALUES (%s, %s, %s, %s, %s)",
                (username, hash_password(PASSWORD), nickname, "active", 0),
            )
            user_id = cursor.lastrowid
    conn.commit()
    return user_id


def clear_existing_eval_ratings(conn, user_ids):
    if not user_ids:
        return
    placeholders = ", ".join(["%s"] * len(user_ids))
    with conn.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM user_movie_ratings WHERE user_id IN ({placeholders})",
            user_ids,
        )
    conn.commit()


def reset_neo4j_user_edges(user_ids):
    if not user_ids:
        return
    driver = Neo4jConnection.get_driver()
    with driver.session() as session:
        session.run(
            """
            UNWIND $user_ids AS uid
            MATCH (u:User {id: uid})-[rel:RATED]->()
            DELETE rel
            """,
            user_ids=user_ids,
        ).consume()


def write_user_ratings(conn, user_id: int, username: str, ratings):
    driver = Neo4jConnection.get_driver()
    with driver.session() as session:
        session.run(
            "MERGE (u:User {id: $uid}) SET u.username = $username, u.is_mock = false",
            uid=user_id,
            username=username,
        ).consume()
        for index, (movie, rating) in enumerate(ratings):
            rated_at = START_DATE + timedelta(days=index)
            comment = f"eval_real_seed:{movie['name']}"
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO user_movie_ratings (user_id, mid, rating, comment_short, rated_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        rating = VALUES(rating),
                        comment_short = VALUES(comment_short),
                        rated_at = VALUES(rated_at),
                        updated_at = VALUES(updated_at)
                    """,
                    (user_id, movie["douban_id"], rating, comment, rated_at, rated_at),
                )
            session.run(
                """
                MATCH (u:User {id: $uid}), (m:Movie {mid: $mid})
                MERGE (u)-[rel:RATED]->(m)
                SET rel.rating = $rating, rel.timestamp = datetime($timestamp)
                """,
                uid=user_id,
                mid=movie["douban_id"],
                rating=rating,
                timestamp=rated_at.isoformat(),
            ).consume()
    conn.commit()


def seed_eval_real_users():
    random.seed(RANDOM_SEED)
    init_pool()
    conn = get_connection()
    try:
        movies = load_movie_pool(conn)
        user_specs = []
        for persona in PERSONAS:
            persona_pool = build_persona_pool(movies, persona)
            for user_index in range(USERS_PER_PERSONA):
                username = f"eval_real_{persona['slug']}_{user_index + 1}"
                nickname = f"{persona['label']}{user_index + 1}"
                user_id = upsert_eval_user(conn, username, nickname)
                ratings = build_rating_plan(persona_pool, user_index)
                user_specs.append({
                    "user_id": user_id,
                    "username": username,
                    "ratings": ratings,
                })

        user_ids = [spec["user_id"] for spec in user_specs]
        clear_existing_eval_ratings(conn, user_ids)
        reset_neo4j_user_edges(user_ids)

        total_ratings = 0
        for spec in user_specs:
            write_user_ratings(conn, spec["user_id"], spec["username"], spec["ratings"])
            total_ratings += len(spec["ratings"])

        print({
            "seeded_users": len(user_specs),
            "seeded_ratings": total_ratings,
            "usernames": [spec["username"] for spec in user_specs[:5]],
        })
    finally:
        conn.close()
        close_pool()
        Neo4jConnection.close()


if __name__ == "__main__":
    seed_eval_real_users()
