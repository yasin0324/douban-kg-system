"""
用户行为服务 — 偏好（喜欢/想看）+ 评分 CRUD + 用户画像分析 + 用户画像图谱
"""
import time
from collections import Counter, defaultdict
from datetime import date
from typing import Optional


def add_preference(conn, user_id: int, mid: str, pref_type: str) -> dict:
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO user_movie_prefs (user_id, mid, pref_type) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE pref_type = VALUES(pref_type), updated_at = NOW()",
            (user_id, mid, pref_type),
        )
        conn.commit()
        cursor.execute(
            "SELECT id, mid, pref_type, created_at FROM user_movie_prefs WHERE user_id = %s AND mid = %s",
            (user_id, mid),
        )
        return cursor.fetchone()


def remove_preference(conn, user_id: int, mid: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM user_movie_prefs WHERE user_id = %s AND mid = %s",
            (user_id, mid),
        )
        conn.commit()
        return cursor.rowcount > 0


def list_preferences(conn, user_id: int, pref_type: Optional[str] = None, page: int = 1, size: int = 20) -> dict:
    offset = (page - 1) * size
    with conn.cursor() as cursor:
        where = "WHERE user_id = %s"
        params: list = [user_id]
        if pref_type:
            where += " AND pref_type = %s"
            params.append(pref_type)

        cursor.execute(
            f"SELECT COUNT(*) as total FROM user_movie_prefs {where}",
            params,
        )
        total = cursor.fetchone()["total"]

        cursor.execute(
            f"SELECT id, mid, pref_type, created_at FROM user_movie_prefs {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            params + [size, offset],
        )
        items = cursor.fetchall()
    return {"items": items, "total": total, "page": page, "size": size}


def check_preference(conn, user_id: int, mid: str) -> dict:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT pref_type FROM user_movie_prefs WHERE user_id = %s AND mid = %s",
            (user_id, mid),
        )
        row = cursor.fetchone()
    return {
        "mid": mid,
        "is_liked": row is not None and row["pref_type"] == "like",
        "is_want_to_watch": row is not None and row["pref_type"] == "want_to_watch",
    }


def check_movie_released(conn, mid: str):
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT name, year, release_date FROM movies WHERE douban_id = %s",
            (mid,),
        )
        movie = cursor.fetchone()

    if not movie:
        raise ValueError("电影不存在")

    year = movie.get("year")
    release_date_str = movie.get("release_date")
    if release_date_str:
        release_date_str = release_date_str[:10]

    today = date.today()
    current_date = today.isoformat()
    current_year = today.year
    is_unreleased = False
    if year and year > current_year:
        is_unreleased = True
    elif year == current_year:
        if not release_date_str:
            is_unreleased = True
        elif release_date_str > current_date:
            is_unreleased = True

    if is_unreleased:
        raise ValueError("按理来说未上映的电影或剧集不能进行评分")


def add_rating(conn, user_id: int, mid: str, rating: float, comment_short: str = None) -> dict:
    check_movie_released(conn, mid)
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO user_movie_ratings (user_id, mid, rating, comment_short) VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE rating = VALUES(rating), comment_short = VALUES(comment_short), updated_at = NOW()",
            (user_id, mid, rating, comment_short),
        )
        conn.commit()
        cursor.execute(
            "SELECT id, mid, rating, comment_short, rated_at FROM user_movie_ratings WHERE user_id = %s AND mid = %s",
            (user_id, mid),
        )
        return cursor.fetchone()


def remove_rating(conn, user_id: int, mid: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM user_movie_ratings WHERE user_id = %s AND mid = %s",
            (user_id, mid),
        )
        conn.commit()
        return cursor.rowcount > 0


def list_ratings(conn, user_id: int, page: int = 1, size: int = 20) -> dict:
    offset = (page - 1) * size
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) as total FROM user_movie_ratings WHERE user_id = %s",
            (user_id,),
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT id, mid, rating, comment_short, rated_at FROM user_movie_ratings "
            "WHERE user_id = %s ORDER BY rated_at DESC LIMIT %s OFFSET %s",
            (user_id, size, offset),
        )
        items = cursor.fetchall()
    return {"items": items, "total": total, "page": page, "size": size}


def get_rating(conn, user_id: int, mid: str) -> Optional[dict]:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, mid, rating, comment_short, rated_at FROM user_movie_ratings WHERE user_id = %s AND mid = %s",
            (user_id, mid),
        )
        return cursor.fetchone()


COLD_START_THRESHOLD = 3


def _split_pref_mids(pref_rows: list[dict]) -> tuple[set[str], set[str]]:
    liked_mids = set()
    want_mids = set()
    for row in pref_rows:
        mid = str(row["mid"])
        if row["pref_type"] == "like":
            liked_mids.add(mid)
        elif row["pref_type"] == "want_to_watch":
            want_mids.add(mid)
    return liked_mids, want_mids


def _build_activity_summary(*, rated_mids: set[str], liked_mids: set[str], want_mids: set[str]) -> dict:
    effective = len(rated_mids | liked_mids | want_mids)
    return {
        "liked_count": len(liked_mids),
        "want_to_watch_count": len(want_mids),
        "rating_count": len(rated_mids),
        "effective_signal_count": effective,
        "cold_start": effective < COLD_START_THRESHOLD,
        "meets_personalization_threshold": effective >= COLD_START_THRESHOLD,
    }


def get_activity_summary(conn, user_id: int) -> dict:
    """获取用户行为汇总，用于冷启动判断。

    有效信号按「去重后的电影数」计算：同一电影若同时存在评分和偏好，只计 1 个信号。
    """
    with conn.cursor() as cursor:
        # 评分电影 mid 集合
        cursor.execute(
            "SELECT mid FROM user_movie_ratings WHERE user_id = %s",
            (user_id,),
        )
        rated_mids = {str(row["mid"]) for row in cursor.fetchall()}

        # 偏好电影 mid 集合（按类型分组）
        cursor.execute(
            "SELECT mid, pref_type FROM user_movie_prefs WHERE user_id = %s",
            (user_id,),
        )
        pref_rows = cursor.fetchall()

    liked_mids, want_mids = _split_pref_mids(pref_rows)
    return _build_activity_summary(
        rated_mids=rated_mids,
        liked_mids=liked_mids,
        want_mids=want_mids,
    )


def get_profile_analysis(conn, neo4j_session, user_id: int) -> dict:
    """聚合用户画像分析数据：类型偏好、评分分布、年代分布、常看导演/演员"""
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT mid, rating FROM user_movie_ratings WHERE user_id = %s",
            (user_id,),
        )
        rating_rows = cursor.fetchall()

        cursor.execute(
            "SELECT mid, pref_type FROM user_movie_prefs WHERE user_id = %s",
            (user_id,),
        )
        pref_rows = cursor.fetchall()

    rated_map = {str(r["mid"]): float(r["rating"]) for r in rating_rows}
    liked_mids, want_mids = _split_pref_mids(pref_rows)
    rated_mids = set(rated_map.keys())
    all_mids = list(set(rated_map.keys()) | liked_mids | want_mids)

    summary = {
        **_build_activity_summary(
            rated_mids=rated_mids,
            liked_mids=liked_mids,
            want_mids=want_mids,
        ),
        "avg_rating": round(sum(rated_map.values()) / len(rated_map), 2) if rated_map else 0,
    }

    if not all_mids:
        return {
            "summary": summary,
            "genre_distribution": [],
            "top_directors": [],
            "top_actors": [],
            "tag_cloud": [],
        }

    # 从 Neo4j 查询电影的类型、导演、演员、年代
    result = neo4j_session.run(
        """
        UNWIND $mids AS mid
        MATCH (m:Movie {mid: mid})
        OPTIONAL MATCH (m)-[:HAS_GENRE]->(g:Genre)
        OPTIONAL MATCH (d:Person)-[:DIRECTED]->(m)
        OPTIONAL MATCH (a:Person)-[:ACTED_IN]->(m)
        RETURN m.mid AS mid, m.year AS year,
               collect(DISTINCT g.name) AS genres,
               collect(DISTINCT {pid: d.pid, name: d.name}) AS directors,
               collect(DISTINCT {pid: a.pid, name: a.name}) AS actors
        """,
        mids=all_mids,
    )
    movie_info = {str(r["mid"]): dict(r) for r in result}

    # 类型偏好聚合
    genre_counter = Counter()
    genre_ratings = defaultdict(list)
    for mid, info in movie_info.items():
        for genre in (info.get("genres") or []):
            if not genre:
                continue
            genre_counter[genre] += 1
            if mid in rated_map:
                genre_ratings[genre].append(rated_map[mid])

    genre_distribution = sorted(
        [
            {
                "genre": g,
                "count": c,
                "avg_rating": round(sum(genre_ratings[g]) / len(genre_ratings[g]), 2) if genre_ratings.get(g) else None,
            }
            for g, c in genre_counter.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )

    # 常看导演
    director_counter = Counter()
    director_ratings = defaultdict(list)
    for mid, info in movie_info.items():
        for d in (info.get("directors") or []):
            if not d or not d.get("pid"):
                continue
            director_counter[(d["pid"], d["name"])] += 1
            if mid in rated_map:
                director_ratings[(d["pid"], d["name"])].append(rated_map[mid])

    top_directors = sorted(
        [
            {
                "pid": pid,
                "name": name,
                "count": c,
                "avg_rating": round(sum(director_ratings[(pid, name)]) / len(director_ratings[(pid, name)]), 2)
                if director_ratings.get((pid, name))
                else None,
            }
            for (pid, name), c in director_counter.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )[:10]

    # 常看演员
    actor_counter = Counter()
    actor_ratings = defaultdict(list)
    for mid, info in movie_info.items():
        for a in (info.get("actors") or []):
            if not a or not a.get("pid"):
                continue
            actor_counter[(a["pid"], a["name"])] += 1
            if mid in rated_map:
                actor_ratings[(a["pid"], a["name"])].append(rated_map[mid])

    top_actors = sorted(
        [
            {
                "pid": pid,
                "name": name,
                "count": c,
                "avg_rating": round(sum(actor_ratings[(pid, name)]) / len(actor_ratings[(pid, name)]), 2)
                if actor_ratings.get((pid, name))
                else None,
            }
            for (pid, name), c in actor_counter.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )[:10]

    # 标签云：合并类型、导演、演员，按交互频次加权
    tag_cloud = []
    for g, c in genre_counter.items():
        tag_cloud.append({"text": g, "weight": c * 3, "type": "genre"})
    for (pid, name), c in director_counter.most_common(15):
        tag_cloud.append({"text": name, "weight": c * 2, "type": "director"})
    for (pid, name), c in actor_counter.most_common(20):
        tag_cloud.append({"text": name, "weight": c, "type": "actor"})
    tag_cloud.sort(key=lambda x: x["weight"], reverse=True)

    return {
        "summary": summary,
        "genre_distribution": genre_distribution,
        "top_directors": top_directors,
        "top_actors": top_actors,
        "tag_cloud": tag_cloud,
    }


def get_profile_graph(conn, neo4j_session, user_id: int, username: str, movie_limit: int = 30) -> dict:
    """以用户为中心构建个人观影知识图谱子图"""
    start_time = time.time()
    movie_limit = min(max(movie_limit, 5), 100)
    # 总节点上限按电影数估算（电影 + 影人 + 类型），供最终截断用
    node_limit = min(movie_limit * 5, 1000)

    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT mid, rating FROM user_movie_ratings WHERE user_id = %s ORDER BY rating DESC",
            (user_id,),
        )
        rating_rows = cursor.fetchall()

        cursor.execute(
            "SELECT mid, pref_type FROM user_movie_prefs WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        )
        pref_rows = cursor.fetchall()

    rated_map = {str(r["mid"]): float(r["rating"]) for r in rating_rows}
    liked_mids = [str(r["mid"]) for r in pref_rows if r["pref_type"] == "like"]
    want_mids = [str(r["mid"]) for r in pref_rows if r["pref_type"] == "want_to_watch"]

    ordered_mids = list(dict.fromkeys(
        list(rated_map.keys()) + liked_mids + want_mids
    ))

    selected_mids = ordered_mids[:movie_limit]

    if not selected_mids:
        query_time = int((time.time() - start_time) * 1000)
        return {
            "nodes": [],
            "edges": [],
            "meta": {"depth": 1, "node_count": 0, "edge_count": 0, "truncated": False, "query_time_ms": query_time},
        }

    result = neo4j_session.run(
        """
        UNWIND $mids AS mid
        MATCH (m:Movie {mid: mid})
        OPTIONAL MATCH (m)-[:HAS_GENRE]->(g:Genre)
        OPTIONAL MATCH (d:Person)-[:DIRECTED]->(m)
        OPTIONAL MATCH (a:Person)-[:ACTED_IN]->(m)
        RETURN m.mid AS mid, m.title AS title, m.rating AS rating, m.year AS year,
               collect(DISTINCT {name: g.name}) AS genres,
               collect(DISTINCT {pid: d.pid, name: d.name, profession: d.profession}) AS directors,
               collect(DISTINCT {pid: a.pid, name: a.name, profession: a.profession}) AS actors
        """,
        mids=selected_mids,
    )
    movie_data = {str(r["mid"]): dict(r) for r in result}

    nodes_map = {}
    # key: (source, target, rel_type) → edge_properties dict or None
    edges: dict[tuple, dict | None] = {}

    user_node_id = f"user_{user_id}"
    nodes_map[user_node_id] = {
        "id": user_node_id,
        "label": username or "我",
        "type": "User",
        "properties": None,
    }

    for mid in selected_mids:
        info = movie_data.get(mid)
        if not info:
            continue
        movie_id = f"movie_{mid}"
        props = {}
        if info.get("rating"):
            props["rating"] = info["rating"]
        if info.get("year"):
            props["year"] = info["year"]
        nodes_map[movie_id] = {
            "id": movie_id,
            "label": info.get("title") or mid,
            "type": "Movie",
            "properties": props or None,
        }

        if mid in rated_map:
            edges[(user_node_id, movie_id, "RATED")] = {"rating": rated_map[mid]}
        elif mid in liked_mids:
            edges[(user_node_id, movie_id, "LIKED")] = None
        else:
            edges[(user_node_id, movie_id, "WANT_TO_WATCH")] = None

        for g in (info.get("genres") or []):
            if not g or not g.get("name"):
                continue
            gid = f"genre_{g['name']}"
            if gid not in nodes_map:
                nodes_map[gid] = {"id": gid, "label": g["name"], "type": "Genre", "properties": None}
            edges[(movie_id, gid, "HAS_GENRE")] = None

        for d in (info.get("directors") or []):
            if not d or not d.get("pid"):
                continue
            did = f"person_{d['pid']}"
            if did not in nodes_map:
                p = {}
                if d.get("profession"):
                    p["profession"] = d["profession"]
                nodes_map[did] = {"id": did, "label": d.get("name") or d["pid"], "type": "Person", "properties": p or None}
            edges[(did, movie_id, "DIRECTED")] = None

        for a in (info.get("actors") or []):
            if not a or not a.get("pid"):
                continue
            aid = f"person_{a['pid']}"
            if aid not in nodes_map:
                p = {}
                if a.get("profession"):
                    p["profession"] = a["profession"]
                nodes_map[aid] = {"id": aid, "label": a.get("name") or a["pid"], "type": "Person", "properties": p or None}
            edges[(aid, movie_id, "ACTED_IN")] = None

    nodes = list(nodes_map.values())
    edge_list = [
        {"source": s, "target": t, "type": rt, **({"properties": ep} if ep else {})}
        for (s, t, rt), ep in edges.items()
    ]
    truncated = len(nodes) > node_limit
    nodes = nodes[:node_limit]
    node_ids = {n["id"] for n in nodes}
    edge_list = [e for e in edge_list if e["source"] in node_ids and e["target"] in node_ids]

    query_time = int((time.time() - start_time) * 1000)
    return {
        "nodes": nodes,
        "edges": edge_list,
        "meta": {
            "depth": 1,
            "node_count": len(nodes),
            "edge_count": len(edge_list),
            "truncated": truncated,
            "query_time_ms": query_time,
        },
    }
