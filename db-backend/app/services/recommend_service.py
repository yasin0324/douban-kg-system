"""
推荐服务
"""
from collections import Counter, defaultdict
import logging
import random
from typing import Any, Dict, List

from fastapi import HTTPException

from app.algorithms.common import (
    build_weighted_user_profile,
    dedupe_preserve_order,
    fetch_movie_graph_profile_map,
    run_query,
    score_movie_against_user_profile,
    top_weighted_items,
)
from app.algorithms.cfkg import get_cfkg_recommendations
from app.algorithms.graph_cf import get_graph_cf_recommendations
from app.algorithms.graph_content import get_graph_content_recommendations
from app.algorithms.graph_ppr import get_graph_ppr_recommendations
from app.algorithms.hybrid_manager import manager as hybrid_manager
from app.db.neo4j import Neo4jConnection
from app.services import user_service

logger = logging.getLogger(__name__)

DEFAULT_EXPLAIN_TIMEOUT_MS = 1200
DEFAULT_PROFILE_TIMEOUT_MS = 1000
SOURCE_NAME_MAP = {
    "graph_cfkg": "cfkg",
    "graph_cf": "cf",
    "graph_content": "content",
    "graph_ppr": "ppr",
    "cfkg": "cfkg",
    "cf": "cf",
    "content": "content",
    "ppr": "ppr",
}
RELATION_LABELS = {
    "DIRECTED": "共同导演",
    "ACTED_IN": "共同演员",
    "HAS_GENRE": "共同类型",
}
SIGNAL_LABELS = {
    "cfkg": "CFKG 表示学习信号",
    "cf": "相似用户协同信号",
    "content": "图谱内容相似信号",
    "ppr": "图谱游走信号",
    "hybrid": "混合推荐融合信号",
}
META_PATH_TEMPLATE_LABELS = {
    "HAS_GENRE": "User -> Movie -> Genre -> Movie",
    "DIRECTED": "User -> Movie -> Director -> Movie",
    "ACTED_IN": "User -> Movie -> Actor -> Movie",
}
MOVIE_BRIEF_QUERY = """
UNWIND $movie_ids AS requested_id
MATCH (m:Movie {mid: requested_id})
OPTIONAL MATCH (m)-[:HAS_GENRE]->(g:Genre)
RETURN requested_id,
       m.mid AS mid,
       coalesce(m.title, m.name) AS title,
       m.rating AS rating,
       m.year AS year,
       m.cover AS cover,
       collect(DISTINCT g.name) AS genres
"""
RECOMMEND_EXPLAIN_QUERY = """
MATCH (target:Movie {mid: $target_mid})
UNWIND $representative_ids AS representative_id
MATCH (rep:Movie {mid: representative_id})
OPTIONAL MATCH (rep)-[rep_rel:DIRECTED|ACTED_IN|HAS_GENRE]-(shared)-[target_rel:DIRECTED|ACTED_IN|HAS_GENRE]-(target)
WHERE type(rep_rel) = type(target_rel)
RETURN rep.mid AS representative_mid,
       type(rep_rel) AS rel_type,
       labels(shared)[0] AS shared_type,
       shared.mid AS shared_mid,
       shared.pid AS shared_pid,
       coalesce(shared.name_zh, shared.name, shared.title) AS shared_label,
       shared.rating AS shared_rating,
       shared.year AS shared_year
ORDER BY representative_mid
"""
FALLBACK_CF_QUERY = """
MATCH (:User)-[r:RATED]->(m:Movie)
WHERE r.rating >= 4.0
  AND NOT m.mid IN $seen_movie_ids
RETURN m.mid AS movie_id,
       coalesce(m.title, m.name) AS title,
       count(r) AS crowd_count,
       avg(r.rating) AS avg_rating
ORDER BY crowd_count DESC, avg_rating DESC, movie_id ASC
LIMIT $limit
"""
FALLBACK_CONTENT_QUERY = """
MATCH (m:Movie)
WHERE NOT m.mid IN $seen_movie_ids
OPTIONAL MATCH (m)-[:HAS_GENRE]->(g:Genre)
WITH m, count(DISTINCT g) AS genre_count
RETURN m.mid AS movie_id,
       coalesce(m.title, m.name) AS title,
       coalesce(m.rating, 0.0) AS rating,
       coalesce(m.votes, 0) AS votes,
       genre_count
ORDER BY rating DESC, votes DESC, genre_count DESC, movie_id ASC
LIMIT $limit
"""
FALLBACK_PPR_QUERY = """
MATCH (m:Movie)
WHERE NOT m.mid IN $seen_movie_ids
OPTIONAL MATCH (m)-[:HAS_GENRE|ACTED_IN|DIRECTED]-()
WITH m, count(*) AS graph_degree
RETURN m.mid AS movie_id,
       coalesce(m.title, m.name) AS title,
       graph_degree,
       coalesce(m.rating, 0.0) AS rating,
       coalesce(m.votes, 0) AS votes
ORDER BY graph_degree DESC, rating DESC, votes DESC, movie_id ASC
LIMIT $limit
"""
FALLBACK_HYBRID_QUERY = """
MATCH (m:Movie)
WHERE NOT m.mid IN $seen_movie_ids
OPTIONAL MATCH (m)-[:HAS_GENRE|ACTED_IN|DIRECTED]-()
WITH m, count(*) AS graph_degree
RETURN m.mid AS movie_id,
       coalesce(m.title, m.name) AS title,
       (
         coalesce(m.rating, 0.0) * 0.72 +
         toFloat(graph_degree) * 0.08 +
         sqrt(toFloat(coalesce(m.votes, 0)) + 1.0) * 0.05
       ) AS hybrid_score,
       graph_degree,
       coalesce(m.rating, 0.0) AS rating,
       coalesce(m.votes, 0) AS votes
ORDER BY hybrid_score DESC, movie_id ASC
LIMIT $limit
"""


def _fetch_movie_brief_map(movie_ids: List[str], timeout_ms: int | None = None) -> Dict[str, Dict[str, Any]]:
    requested_ids = dedupe_preserve_order(movie_ids)
    if not requested_ids:
        return {}

    return _fetch_movie_brief_map_from_neo4j(requested_ids, timeout_ms=timeout_ms)


def _fetch_movie_brief_map_from_neo4j(
    requested_ids: List[str],
    timeout_ms: int | None = None,
) -> Dict[str, Dict[str, Any]]:
    driver = Neo4jConnection.get_driver()
    with driver.session() as session:
        records = run_query(
            session,
            MOVIE_BRIEF_QUERY,
            timeout_ms=timeout_ms,
            movie_ids=requested_ids,
        )

    brief_map: Dict[str, Dict[str, Any]] = {}
    for record in records:
        brief_map[record["requested_id"]] = {
            "mid": record["mid"],
            "title": record["title"],
            "rating": float(record["rating"]) if record.get("rating") is not None else None,
            "year": int(record["year"]) if record.get("year") is not None else None,
            "cover": record.get("cover"),
            "genres": [genre for genre in record.get("genres", []) if genre],
        }
    return brief_map


def _fetch_movie_brief_map_from_mysql(conn, movie_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    requested_ids = dedupe_preserve_order(movie_ids)
    if not requested_ids:
        return {}

    placeholders = ",".join(["%s"] * len(requested_ids))
    query = f"""
        SELECT douban_id AS mid,
               name AS title,
               douban_score AS rating,
               year,
               cover,
               genres
        FROM movies
        WHERE douban_id IN ({placeholders})
    """
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(requested_ids))
        rows = cursor.fetchall()

    row_map: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        mid = str(row["mid"])
        row_map[mid] = {
            "mid": mid,
            "title": row.get("title") or mid,
            "rating": float(row["rating"]) if row.get("rating") is not None else None,
            "year": int(row["year"]) if row.get("year") is not None else None,
            "cover": row.get("cover"),
            "genres": [
                genre.strip()
                for genre in str(row.get("genres") or "").replace(" / ", "/").split("/")
                if genre.strip()
            ],
        }
    return row_map


def _fetch_movie_brief_map_safe(
    conn,
    movie_ids: List[str],
    timeout_ms: int | None = None,
) -> Dict[str, Dict[str, Any]]:
    requested_ids = dedupe_preserve_order(movie_ids)
    if not requested_ids:
        return {}

    try:
        return _fetch_movie_brief_map_from_neo4j(requested_ids, timeout_ms=timeout_ms)
    except Exception:
        logger.warning("Neo4j movie brief query failed, falling back to MySQL", exc_info=True)
        return _fetch_movie_brief_map_from_mysql(conn, requested_ids)


def _collect_profile_highlights(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    positive_features = profile.get("positive_features", {})
    feature_labels = profile.get("feature_labels", {})
    highlights = []

    for genre in top_weighted_items(positive_features.get("genres", {}), 2):
        highlights.append({"type": "genre", "label": genre})
    for director_id in top_weighted_items(positive_features.get("directors", {}), 1):
        highlights.append({
            "type": "director",
            "label": feature_labels.get("directors", {}).get(director_id, director_id),
        })
    for actor_id in top_weighted_items(positive_features.get("actors", {}), 1):
        highlights.append({
            "type": "actor",
            "label": feature_labels.get("actors", {}).get(actor_id, actor_id),
        })
    for region in top_weighted_items(positive_features.get("regions", {}), 1):
        highlights.append({"type": "region", "label": region})

    deduped = []
    seen = set()
    for item in highlights:
        if item["label"] in seen:
            continue
        seen.add(item["label"])
        deduped.append(item)
    return deduped[:5]


def _build_user_profile(conn, user_id: int) -> Dict[str, Any]:
    raw_profile = user_service.build_user_recommendation_profile(conn, user_id)
    movie_ids = dedupe_preserve_order(
        raw_profile["positive_movie_ids"]
        + raw_profile["negative_movie_ids"]
        + raw_profile["representative_movie_ids"],
    )
    movie_profile_map = fetch_movie_graph_profile_map(
        Neo4jConnection.get_driver(),
        movie_ids,
        timeout_ms=DEFAULT_PROFILE_TIMEOUT_MS,
    )
    weighted_profile = build_weighted_user_profile(
        movie_profile_map,
        raw_profile["movie_feedback"],
    )
    profile = {
        **raw_profile,
        **weighted_profile,
    }
    profile["profile_highlights"] = _collect_profile_highlights(profile)
    return profile


async def _dispatch_personal_algorithm(
    algorithm: str,
    user_id: int,
    user_profile: Dict[str, Any],
    seen_movie_ids: List[str],
    limit: int,
) -> List[Dict[str, Any]]:
    if algorithm == "cfkg":
        return await get_cfkg_recommendations(
            user_id=user_id,
            user_profile=user_profile,
            seen_movie_ids=seen_movie_ids,
            limit=limit,
        )
    if algorithm == "ppr":
        return await get_graph_ppr_recommendations(
            user_id=user_id,
            user_profile=user_profile,
            seen_movie_ids=seen_movie_ids,
            limit=limit,
        )
    if algorithm == "content":
        return await get_graph_content_recommendations(
            user_id=user_id,
            user_profile=user_profile,
            seen_movie_ids=seen_movie_ids,
            limit=limit,
        )
    if algorithm == "cf":
        return await get_graph_cf_recommendations(
            user_id=user_id,
            user_profile=user_profile,
            seen_movie_ids=seen_movie_ids,
            limit=limit,
        )
    if algorithm == "hybrid":
        return await hybrid_manager.get_hybrid_recommendations(
            user_id=user_id,
            user_profile=user_profile,
            seen_movie_ids=seen_movie_ids,
            limit=limit,
        )
    raise HTTPException(status_code=400, detail="不支持的算法类型")


def _normalize_source_algorithms(item: Dict[str, Any], algorithm: str) -> List[str]:
    sources = item.get("source_algorithms")
    if sources:
        return dedupe_preserve_order([
            SOURCE_NAME_MAP.get(source, source.replace("graph_", ""))
            for source in sources
        ])

    source = item.get("source")
    if source:
        return [SOURCE_NAME_MAP.get(source, source.replace("graph_", ""))]

    return [algorithm]


def _normalize_score_breakdown(item: Dict[str, Any]) -> Dict[str, float] | None:
    raw_breakdown = item.get("score_breakdown")
    if not raw_breakdown:
        return None

    breakdown = {}
    for source, score in raw_breakdown.items():
        normalized_source = SOURCE_NAME_MAP.get(source, source.replace("graph_", ""))
        breakdown[normalized_source] = float(score)
    return breakdown


def _get_fallback_query(algorithm: str) -> str:
    if algorithm == "cfkg":
        return FALLBACK_HYBRID_QUERY
    if algorithm == "cf":
        return FALLBACK_CF_QUERY
    if algorithm == "content":
        return FALLBACK_CONTENT_QUERY
    if algorithm == "ppr":
        return FALLBACK_PPR_QUERY
    return FALLBACK_HYBRID_QUERY


def _build_fallback_reason(algorithm: str, record: Dict[str, Any]) -> List[str]:
    if algorithm == "cfkg":
        return ["当前根据口碑、热度与图谱结构信号，为你补充了稳定的推荐候选"]
    if algorithm == "cf":
        return [f"当前优先参考大众高分行为，已有 {int(record.get('crowd_count') or 0)} 位用户给出高分"]
    if algorithm == "content":
        return ["当前优先推荐口碑稳定、类型特征清晰的电影"]
    if algorithm == "ppr":
        return ["当前优先推荐图谱连接度高、关联路径丰富的电影"]
    return ["当前根据综合口碑、热度与图谱结构信号补充推荐结果"]


def _normalize_fallback_score(algorithm: str, record: Dict[str, Any]) -> float:
    if record.get("hybrid_score") is not None:
        return float(record.get("hybrid_score") or 0)
    if algorithm == "cfkg":
        return float(record.get("hybrid_score") or 0)
    if algorithm == "cf":
        return float(record.get("crowd_count") or 0) + float(record.get("avg_rating") or 0)
    if algorithm == "content":
        return float(record.get("rating") or 0) + float(record.get("votes") or 0) * 0.00002
    if algorithm == "ppr":
        return float(record.get("graph_degree") or 0) * 0.05 + float(record.get("rating") or 0)
    return float(record.get("hybrid_score") or 0)


def _get_fallback_recommendations(
    algorithm: str,
    seen_movie_ids: List[str],
    limit: int,
    conn=None,
) -> List[Dict[str, Any]]:
    deduped_seen_movie_ids = dedupe_preserve_order(seen_movie_ids)
    try:
        driver = Neo4jConnection.get_driver()
        with driver.session() as session:
            records = run_query(
                session,
                _get_fallback_query(algorithm),
                timeout_ms=DEFAULT_EXPLAIN_TIMEOUT_MS,
                seen_movie_ids=deduped_seen_movie_ids,
                limit=limit,
            )
    except Exception:
        if conn is None:
            raise
        logger.warning(
            "Neo4j fallback query failed for algorithm=%s, falling back to MySQL",
            algorithm,
            exc_info=True,
        )
        records = _get_mysql_fallback_recommendations(
            conn=conn,
            seen_movie_ids=deduped_seen_movie_ids,
            limit=limit,
        )

    return [
        {
            "movie_id": record["movie_id"],
            "title": record.get("title", ""),
            "score": _normalize_fallback_score(algorithm, record),
            "reasons": _build_fallback_reason(algorithm, record),
            "source": algorithm,
        }
        for record in records
    ]


def _get_mysql_fallback_recommendations(
    conn,
    seen_movie_ids: List[str],
    limit: int,
) -> List[Dict[str, Any]]:
    deduped_seen_movie_ids = dedupe_preserve_order(seen_movie_ids)
    params: List[Any] = []
    exclude_clause = ""
    if deduped_seen_movie_ids:
        placeholders = ",".join(["%s"] * len(deduped_seen_movie_ids))
        exclude_clause = f"AND douban_id NOT IN ({placeholders})"
        params.extend(deduped_seen_movie_ids)

    query = f"""
        SELECT douban_id AS movie_id,
               name AS title,
               douban_score AS rating,
               douban_votes AS votes,
               (
                 (50000 * 7.0 + COALESCE(douban_votes, 0) * COALESCE(douban_score, 0.0))
                 / (50000 + COALESCE(douban_votes, 0))
               ) AS hybrid_score
        FROM movies
        WHERE type = 'movie'
          AND douban_score IS NOT NULL
          {exclude_clause}
        ORDER BY hybrid_score DESC, COALESCE(douban_votes, 0) DESC, douban_id ASC
        LIMIT %s
    """
    params.append(limit)
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(params))
        return cursor.fetchall()


def _normalize_recommendation_items(
    raw_items: List[Dict[str, Any]],
    brief_map: Dict[str, Dict[str, Any]],
    algorithm: str,
) -> List[Dict[str, Any]]:
    normalized_items = []
    for item in raw_items:
        movie_id = item["movie_id"]
        movie_brief = brief_map.get(movie_id, {
            "mid": movie_id,
            "title": item.get("title") or movie_id,
            "rating": None,
            "year": None,
            "cover": None,
            "genres": [],
        })
        normalized_item = {
            "movie": movie_brief,
            "score": float(item.get("final_score", item.get("score", 0.0))),
            "reasons": dedupe_preserve_order(item.get("reasons", []))[:3],
            "source_algorithms": _normalize_source_algorithms(item, algorithm),
            "negative_signals": dedupe_preserve_order(item.get("negative_signals", []))[:2],
        }
        score_breakdown = _normalize_score_breakdown(item)
        if score_breakdown:
            normalized_item["score_breakdown"] = score_breakdown
        normalized_items.append(normalized_item)
    normalized_items.sort(key=lambda item: (-item["score"], item["movie"]["mid"]))
    return normalized_items


def _apply_reroll_order(
    items: List[Dict[str, Any]],
    limit: int,
    reroll_token: str | None = None,
) -> List[Dict[str, Any]]:
    if not reroll_token:
        return items[:limit]

    rng = random.Random(str(reroll_token))
    pool = list(items)
    selected = []
    seen_genres = Counter()

    while pool and len(selected) < limit:
        best_index = 0
        best_score = None
        for index, item in enumerate(pool[:24]):
            genres = item["movie"].get("genres", [])
            diversity_penalty = sum(seen_genres[genre] for genre in genres) * 0.08
            exploration_bonus = rng.uniform(0.0, 0.18) + min(index, 12) * 0.012
            adjusted_score = item["score"] - diversity_penalty + exploration_bonus
            if best_score is None or adjusted_score > best_score:
                best_score = adjusted_score
                best_index = index
        picked = pool.pop(best_index)
        selected.append(picked)
        for genre in picked["movie"].get("genres", []):
            seen_genres[genre] += 1

    return selected


def _merge_unique_items(
    primary_items: List[Dict[str, Any]],
    secondary_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged = []
    seen_movie_ids = set()
    for item in primary_items + secondary_items:
        movie_id = item.get("movie_id")
        if not movie_id or movie_id in seen_movie_ids:
            continue
        seen_movie_ids.add(movie_id)
        merged.append(item)
    return merged


def _normalize_requested_algorithm(algorithm: str | None) -> str:
    if not algorithm:
        return "cfkg"
    normalized = str(algorithm).lower().strip()
    if normalized == "hybrid":
        return "cfkg"
    return normalized


async def build_personal_recommendation_payload(
    conn,
    user_id: int,
    algorithm: str = "cfkg",
    limit: int = 20,
    exclude_movie_ids: List[str] | None = None,
    reroll_token: str | None = None,
) -> Dict[str, Any]:
    algorithm = _normalize_requested_algorithm(algorithm)
    user_profile = _build_user_profile(conn, user_id)
    cold_start = bool(user_profile["summary"]["cold_start"])
    hard_excludes = dedupe_preserve_order(user_profile["hard_exclude_movie_ids"])
    reroll_excludes = dedupe_preserve_order(exclude_movie_ids)
    seen_movie_ids = dedupe_preserve_order(hard_excludes + reroll_excludes)

    fallback_used = cold_start and algorithm == "cfkg"
    candidate_limit = min(max(limit * 4, 80), 220)
    raw_items: List[Dict[str, Any]] = []

    if not fallback_used:
        raw_items = await _dispatch_personal_algorithm(
            algorithm=algorithm,
            user_id=user_id,
            user_profile=user_profile,
            seen_movie_ids=seen_movie_ids,
            limit=candidate_limit,
        )
        if not raw_items:
            fallback_used = True
        elif cold_start and algorithm != "cfkg" and len(raw_items) < max(4, limit // 2):
            fallback_items = _get_fallback_recommendations(
                algorithm=algorithm,
                seen_movie_ids=seen_movie_ids,
                limit=max(limit * 2, 20),
                conn=conn,
            )
            raw_items = _merge_unique_items(raw_items, fallback_items)

    if fallback_used:
        raw_items = _get_fallback_recommendations(
            algorithm=algorithm,
            seen_movie_ids=seen_movie_ids,
            limit=max(limit * 3, 30),
            conn=conn,
        )

    movie_ids = [item["movie_id"] for item in raw_items]
    brief_map = _fetch_movie_brief_map_safe(conn, movie_ids, timeout_ms=DEFAULT_EXPLAIN_TIMEOUT_MS)
    normalized_items = _normalize_recommendation_items(
        raw_items,
        brief_map,
        algorithm,
    )
    ordered_items = _apply_reroll_order(
        normalized_items,
        limit=limit,
        reroll_token=reroll_token,
    )

    return {
        "algorithm": algorithm,
        "cold_start": cold_start,
        "generation_mode": "cold_start" if fallback_used else "profile",
        "profile_summary": user_profile["summary"],
        "profile_highlights": user_profile["profile_highlights"],
        "items": ordered_items,
    }


def build_recommendation_explain_payload(
    conn,
    user_id: int,
    target_mid: str,
    algorithm: str = "cfkg",
) -> Dict[str, Any]:
    algorithm = _normalize_requested_algorithm(algorithm)
    user_profile = _build_user_profile(conn, user_id)
    representative_ids = dedupe_preserve_order(
        user_profile.get("representative_movie_ids") or [],
    )[:4]
    brief_map = _fetch_movie_brief_map(
        [target_mid] + representative_ids,
        timeout_ms=DEFAULT_EXPLAIN_TIMEOUT_MS,
    )
    if target_mid not in brief_map:
        raise HTTPException(status_code=404, detail="目标电影不存在")

    target_profile_map = fetch_movie_graph_profile_map(
        Neo4jConnection.get_driver(),
        [target_mid],
        timeout_ms=DEFAULT_EXPLAIN_TIMEOUT_MS,
    )
    target_profile = target_profile_map.get(target_mid)
    profile_reasons, negative_signals = [], []
    if target_profile:
        _, profile_reasons, negative_signals = score_movie_against_user_profile(
            target_profile,
            user_profile,
        )

    valid_representative_ids = [
        movie_id for movie_id in representative_ids if movie_id in brief_map
    ]
    nodes_map: Dict[str, Dict[str, Any]] = {}
    edges_set = set()
    matched_entities = defaultdict(set)
    representative_reason_groups = defaultdict(set)

    target_node_id = f"movie_{target_mid}"
    target_brief = brief_map[target_mid]
    nodes_map[target_node_id] = {
        "id": target_node_id,
        "label": target_brief["title"],
        "type": "Movie",
        "properties": {
            "rating": target_brief["rating"],
            "year": target_brief["year"],
            "cover": target_brief["cover"],
        },
    }
    for movie_id in valid_representative_ids:
        rep_brief = brief_map[movie_id]
        nodes_map[f"movie_{movie_id}"] = {
            "id": f"movie_{movie_id}",
            "label": rep_brief["title"],
            "type": "Movie",
            "properties": {
                "rating": rep_brief["rating"],
                "year": rep_brief["year"],
                "cover": rep_brief["cover"],
            },
        }

    records = []
    if valid_representative_ids:
        driver = Neo4jConnection.get_driver()
        with driver.session() as session:
            records = run_query(
                session,
                RECOMMEND_EXPLAIN_QUERY,
                timeout_ms=DEFAULT_EXPLAIN_TIMEOUT_MS,
                target_mid=target_mid,
                representative_ids=valid_representative_ids,
            )

    for record in records:
        shared_label = record.get("shared_label")
        rel_type = record.get("rel_type")
        if not shared_label or not rel_type:
            continue

        shared_type = record.get("shared_type") or "Unknown"
        raw_shared_id = record.get("shared_mid") or record.get("shared_pid") or shared_label
        shared_node_id = f"{shared_type.lower()}_{raw_shared_id}"
        nodes_map[shared_node_id] = {
            "id": shared_node_id,
            "label": shared_label,
            "type": shared_type,
            "properties": {
                "rating": record.get("shared_rating"),
                "year": record.get("shared_year"),
            },
        }
        edges_set.add((f"movie_{record['representative_mid']}", shared_node_id, rel_type))
        edges_set.add((shared_node_id, target_node_id, rel_type))
        matched_entities[rel_type].add(shared_label)
        representative_reason_groups[(record["representative_mid"], rel_type)].add(shared_label)

    if not representative_reason_groups:
        signal_node_id = f"signal_{algorithm}"
        nodes_map[signal_node_id] = {
            "id": signal_node_id,
            "label": SIGNAL_LABELS.get(algorithm, "推荐信号"),
            "type": "Signal",
            "properties": None,
        }
        edges_set.add((signal_node_id, target_node_id, f"{algorithm.upper()}_SIGNAL"))
        for index, highlight in enumerate(user_profile["profile_highlights"][:3]):
            preference_node_id = f"preference_{index}"
            nodes_map[preference_node_id] = {
                "id": preference_node_id,
                "label": highlight["label"],
                "type": "Preference",
                "properties": {"kind": highlight["type"]},
            }
            edges_set.add((preference_node_id, signal_node_id, "PROFILE_HINT"))

    reason_paths = []
    for (movie_id, rel_type), items in sorted(representative_reason_groups.items()):
        reason_paths.append({
            "representative_mid": movie_id,
            "representative_title": brief_map[movie_id]["title"],
            "relation_type": rel_type,
            "relation_label": RELATION_LABELS.get(rel_type, rel_type),
            "template": META_PATH_TEMPLATE_LABELS.get(rel_type),
            "matched_entities": sorted(items)[:4],
        })

    entity_groups = []
    for rel_type, items in matched_entities.items():
        entity_groups.append({
            "type": RELATION_LABELS.get(rel_type, rel_type),
            "items": sorted(items)[:6],
        })

    return {
        "algorithm": algorithm,
        "target_movie": target_brief,
        "representative_movies": [
            brief_map[movie_id] for movie_id in valid_representative_ids
        ],
        "profile_highlights": user_profile["profile_highlights"],
        "profile_reasons": profile_reasons[:3],
        "negative_signals": negative_signals[:2],
        "nodes": list(nodes_map.values()),
        "edges": [
            {"source": source, "target": target, "type": edge_type}
            for source, target, edge_type in sorted(edges_set)
        ],
        "reason_paths": reason_paths,
        "matched_entities": entity_groups,
        "meta": {
            "has_graph_evidence": bool(representative_reason_groups),
            "representative_movie_count": len(valid_representative_ids),
            "cold_start": bool(user_profile["summary"]["cold_start"]),
        },
    }
