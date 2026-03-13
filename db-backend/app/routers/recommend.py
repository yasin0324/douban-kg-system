"""
推荐系统路由 — 个性化推荐、推荐解释、离线评估
"""

import asyncio
import glob
import logging
from collections import defaultdict
from functools import partial
from threading import BoundedSemaphore, Lock
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.algorithms import ALGORITHMS, ALGORITHM_NAMES
from app.algorithms.graph_cache import (
    GraphMetadataCache,
    MovieGraphProfile,
    REL_ACTOR,
    REL_DIRECTOR,
    REL_GENRE,
    safe_idf,
)
from app.config import settings
from app.db.mysql import get_connection
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommend", tags=["推荐系统"])

RECOMMEND_TIMEOUT_SECONDS = max(float(settings.RECOMMEND_TIMEOUT_SECONDS), 1.0)
RECOMMEND_MAX_CONCURRENT_JOBS = max(
    int(settings.RECOMMEND_MAX_CONCURRENT_JOBS_PER_ALGORITHM),
    1,
)

_runtime_lock = Lock()
_algorithm_instances: dict[str, object] = {}
_algorithm_slots: dict[str, BoundedSemaphore] = {}

EXPLAIN_RELATION_ORDER = (
    REL_DIRECTOR,
    REL_ACTOR,
    REL_GENRE,
)
EXPLAIN_RELATION_WEIGHTS = {
    REL_DIRECTOR: 1.0,
    REL_ACTOR: 0.6,
    REL_GENRE: 0.4,
}
EXPLAIN_RELATION_LABELS = {
    REL_DIRECTOR: "共同导演",
    REL_ACTOR: "共同演员",
    REL_GENRE: "同类类型",
}
EXPLAIN_GROUP_LABELS = {
    REL_DIRECTOR: "导演",
    REL_ACTOR: "演员",
    REL_GENRE: "类型",
}


def _get_algorithm_instance(algo_name: str):
    with _runtime_lock:
        algo = _algorithm_instances.get(algo_name)
        if algo is None:
            algo = ALGORITHMS[algo_name]()
            _algorithm_instances[algo_name] = algo
        return algo


def _get_algorithm_slot(algo_name: str) -> BoundedSemaphore:
    with _runtime_lock:
        slot = _algorithm_slots.get(algo_name)
        if slot is None:
            slot = BoundedSemaphore(RECOMMEND_MAX_CONCURRENT_JOBS)
            _algorithm_slots[algo_name] = slot
        return slot


def _reset_algorithm_runtime_state():
    with _runtime_lock:
        _algorithm_instances.clear()
        _algorithm_slots.clear()


def _run_recommendation_job(algo, slot: BoundedSemaphore, *, user_id: int, n: int, exclude_mids: set[str]):
    try:
        return algo.recommend(
            user_id=user_id,
            n=n,
            exclude_mids=exclude_mids,
        )
    finally:
        slot.release()


def _node_payload(node_id: str, label: str, node_type: str, properties: dict | None = None) -> dict:
    return {
        "id": node_id,
        "label": label,
        "type": node_type,
        "properties": properties or None,
    }


def _graph_token(value: str) -> str:
    return str(value).replace("/", "-").replace(" ", "-")


def _movie_node_payload(
    *,
    mid: str,
    title: str,
    year: int | None = None,
    rating: float | None = None,
) -> dict:
    properties = {}
    if year:
        properties["year"] = year
    if rating is not None:
        properties["rating"] = rating
    return _node_payload(f"movie_{mid}", title, "Movie", properties)


def _person_node_payload(pid: str, name: str) -> dict:
    return _node_payload(f"person_{pid}", name, "Person")


def _genre_node_payload(name: str) -> dict:
    return _node_payload(f"genre_{name}", name, "Genre")


def _signal_node_payload(relation: str, entity_name: str) -> dict:
    return _node_payload(
        f"signal_{relation}_{_graph_token(entity_name)}",
        f"{EXPLAIN_RELATION_LABELS[relation]} {entity_name}",
        "Signal",
    )


def _entity_name(relation: str, entity_id: str) -> str:
    if relation in {REL_DIRECTOR, REL_ACTOR}:
        return GraphMetadataCache.person_name(entity_id)
    return str(entity_id)


def _relation_entities(profile: MovieGraphProfile, relation: str) -> set[str]:
    if relation == REL_ACTOR:
        return profile.relation_entities(relation, actor_top_only=True)
    return profile.relation_entities(relation)


def _reason_template(relation: str, entity_names: list[str]) -> str:
    if not entity_names:
        return EXPLAIN_RELATION_LABELS[relation]
    if relation == REL_GENRE:
        return f"与偏好影片同属 {' / '.join(entity_names[:3])}"
    return f"{EXPLAIN_RELATION_LABELS[relation]} {' / '.join(entity_names[:3])}"


def _load_positive_movies_for_user(user_id: int, algo_name: str) -> list[dict]:
    if algo_name not in ALGORITHMS:
        return []
    algo = _get_algorithm_instance(algo_name)
    conn = get_connection()
    try:
        return algo.get_user_positive_movies(conn, user_id)
    finally:
        conn.close()


def _build_overlap_explanation(
    *,
    target_movie: dict,
    positive_movies: list[dict],
) -> dict:
    GraphMetadataCache.ensure_loaded()
    profiles = GraphMetadataCache.movie_profiles()
    target_mid = str(target_movie["mid"])
    target_profile = profiles.get(target_mid)
    if not target_profile or not positive_movies:
        return {"nodes": [], "edges": [], "reason_paths": [], "matched_entities": []}

    evidence_records = []
    for movie in positive_movies:
        seed_mid = str(movie["mid"])
        if seed_mid == target_mid:
            continue
        seed_profile = profiles.get(seed_mid)
        if not seed_profile:
            continue
        seed_weight = float(movie.get("rating") or 0) / 5.0
        if seed_weight <= 0:
            continue

        for relation in EXPLAIN_RELATION_ORDER:
            shared_entities = sorted(
                _relation_entities(target_profile, relation)
                & _relation_entities(seed_profile, relation)
            )
            for entity_id in shared_entities[:3]:
                entity_name = _entity_name(relation, entity_id)
                evidence_records.append(
                    {
                        "seed_mid": seed_mid,
                        "seed_title": seed_profile.name,
                        "seed_year": seed_profile.year,
                        "relation": relation,
                        "entity_id": str(entity_id),
                        "entity_name": entity_name,
                        "score": seed_weight
                        * EXPLAIN_RELATION_WEIGHTS[relation]
                        * safe_idf(GraphMetadataCache.entity_degree(relation, entity_id)),
                    }
                )

    if not evidence_records:
        return {"nodes": [], "edges": [], "reason_paths": [], "matched_entities": []}

    evidence_records.sort(
        key=lambda item: (
            item["score"],
            item["seed_mid"],
            item["relation"],
            item["entity_name"],
        ),
        reverse=True,
    )
    selected_records = evidence_records[:6]

    nodes_map = {
        f"movie_{target_mid}": _movie_node_payload(
            mid=target_mid,
            title=target_movie["title"],
            year=target_movie.get("year"),
            rating=target_movie.get("rating"),
        )
    }
    edges_set: set[tuple[str, str, str]] = set()
    matched_by_relation: dict[str, list[str]] = defaultdict(list)
    reason_entities: dict[tuple[str, str], list[str]] = defaultdict(list)

    for record in selected_records:
        seed_node_id = f"movie_{record['seed_mid']}"
        nodes_map[seed_node_id] = _movie_node_payload(
            mid=record["seed_mid"],
            title=record["seed_title"],
            year=record.get("seed_year"),
        )

        signal_payload = _signal_node_payload(record["relation"], record["entity_name"])
        signal_id = signal_payload["id"]
        nodes_map[signal_id] = signal_payload

        edges_set.add((seed_node_id, signal_id, "SEED_CONTEXT"))
        edges_set.add((signal_id, f"movie_{target_mid}", "PROFILE_HINT"))

        group = matched_by_relation[record["relation"]]
        if record["entity_name"] not in group:
            group.append(record["entity_name"])

        key = (record["seed_mid"], record["relation"])
        if record["entity_name"] not in reason_entities[key]:
            reason_entities[key].append(record["entity_name"])

    reason_paths = []
    for (seed_mid, relation), entity_names in reason_entities.items():
        seed_title = next(
            (item["seed_title"] for item in selected_records if item["seed_mid"] == seed_mid),
            seed_mid,
        )
        reason_paths.append(
            {
                "relation_type": relation,
                "relation_label": EXPLAIN_RELATION_LABELS[relation],
                "template": _reason_template(relation, entity_names),
                "representative_mid": seed_mid,
                "representative_title": seed_title,
                "matched_entities": entity_names[:3],
            }
        )

    matched_entities = [
        {"type": EXPLAIN_GROUP_LABELS[relation], "items": items[:5]}
        for relation, items in matched_by_relation.items()
        if items
    ]

    edges = [
        {"source": source, "target": target, "type": rel_type}
        for source, target, rel_type in sorted(edges_set)
    ]
    return {
        "nodes": list(nodes_map.values()),
        "edges": edges,
        "reason_paths": reason_paths,
        "matched_entities": matched_entities,
    }


def _build_target_context_explanation(target_movie: dict) -> dict:
    GraphMetadataCache.ensure_loaded()
    profiles = GraphMetadataCache.movie_profiles()
    target_mid = str(target_movie["mid"])
    target_profile = profiles.get(target_mid)
    if not target_profile:
        return {"nodes": [], "edges": [], "reason_paths": [], "matched_entities": []}

    nodes_map = {
        f"movie_{target_mid}": _movie_node_payload(
            mid=target_mid,
            title=target_movie["title"],
            year=target_movie.get("year"),
            rating=target_movie.get("rating"),
        )
    }
    edges_set: set[tuple[str, str, str]] = set()
    matched_entities = []
    reason_paths = []

    directors = sorted(target_profile.directors)[:2]
    if directors:
        names = []
        for pid in directors:
            name = _entity_name(REL_DIRECTOR, pid)
            nodes_map[f"person_{pid}"] = _person_node_payload(pid, name)
            edges_set.add((f"person_{pid}", f"movie_{target_mid}", "DIRECTED"))
            names.append(name)
        matched_entities.append({"type": "导演", "items": names})
        reason_paths.append(
            {
                "relation_type": REL_DIRECTOR,
                "relation_label": "影片导演",
                "template": f"导演 {' / '.join(names)}",
                "representative_mid": target_mid,
                "representative_title": target_movie["title"],
                "matched_entities": names,
            }
        )

    actors = sorted(target_profile.top_actors or target_profile.actors)[:3]
    if actors:
        names = []
        for pid in actors:
            name = _entity_name(REL_ACTOR, pid)
            nodes_map[f"person_{pid}"] = _person_node_payload(pid, name)
            edges_set.add((f"person_{pid}", f"movie_{target_mid}", "ACTED_IN"))
            names.append(name)
        matched_entities.append({"type": "演员", "items": names})
        reason_paths.append(
            {
                "relation_type": REL_ACTOR,
                "relation_label": "核心演员",
                "template": f"演员 {' / '.join(names)}",
                "representative_mid": target_mid,
                "representative_title": target_movie["title"],
                "matched_entities": names,
            }
        )

    genres = sorted(target_profile.genres)[:3]
    if genres:
        for genre in genres:
            nodes_map[f"genre_{genre}"] = _genre_node_payload(genre)
            edges_set.add((f"movie_{target_mid}", f"genre_{genre}", "HAS_GENRE"))
        matched_entities.append({"type": "类型", "items": genres})
        reason_paths.append(
            {
                "relation_type": REL_GENRE,
                "relation_label": "影片类型",
                "template": f"类型 {' / '.join(genres)}",
                "representative_mid": target_mid,
                "representative_title": target_movie["title"],
                "matched_entities": genres,
            }
        )

    edges = [
        {"source": source, "target": target, "type": rel_type}
        for source, target, rel_type in sorted(edges_set)
    ]
    return {
        "nodes": list(nodes_map.values()),
        "edges": edges,
        "reason_paths": reason_paths,
        "matched_entities": matched_entities,
    }


def _build_recommendation_explain_payload(
    *,
    target_movie: dict,
    positive_movies: list[dict],
) -> dict:
    overlap_payload = _build_overlap_explanation(
        target_movie=target_movie,
        positive_movies=positive_movies,
    )
    if overlap_payload["nodes"] and overlap_payload["edges"]:
        return overlap_payload
    return _build_target_context_explanation(target_movie)


@router.get("/personal", summary="个人电影推荐")
async def get_personal_recommendations(
    algorithm: Optional[str] = Query(
        "kg_path",
        description=f"推荐算法: {', '.join(ALGORITHM_NAMES)}",
    ),
    limit: int = Query(20, ge=1, le=50),
    exclude_movie_ids: Optional[List[str]] = Query(None, description="需要排除的电影 ID"),
    user=Depends(get_current_user),
):
    """
    根据指定算法为当前用户生成个性化推荐
    """
    algo_name = (algorithm or "kg_path").lower()
    if algo_name not in ALGORITHMS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的算法: {algo_name}，可选: {', '.join(ALGORITHM_NAMES)}",
        )

    algo_class = ALGORITHMS[algo_name]
    algo = _get_algorithm_instance(algo_name)
    slot = _get_algorithm_slot(algo_name)

    exclude_mids = set(exclude_movie_ids) if exclude_movie_ids else set()
    if not slot.acquire(blocking=False):
        logger.warning("推荐算法 %s 当前繁忙，拒绝用户 %s 的新请求", algo_name, user["id"])
        raise HTTPException(
            status_code=503,
            detail=f"{algo_class.display_name} 当前正在处理中，请稍后重试或切换其他算法",
        )

    try:
        loop = asyncio.get_running_loop()
        try:
            future = loop.run_in_executor(
                None,
                partial(
                    _run_recommendation_job,
                    algo,
                    slot,
                    user_id=user["id"],
                    n=limit,
                    exclude_mids=exclude_mids,
                ),
            )
        except Exception:
            slot.release()
            raise
        recommendations = await asyncio.wait_for(
            future,
            timeout=RECOMMEND_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "推荐算法 %s 对用户 %s 执行超时（%.1fs）",
            algo_name,
            user["id"],
            RECOMMEND_TIMEOUT_SECONDS,
        )
        raise HTTPException(
            status_code=504,
            detail=f"{algo_class.display_name} 计算超时，请稍后重试或切换其他算法",
        )
    except Exception as e:
        logger.error(f"推荐算法 {algo_name} 执行失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"推荐算法执行失败: {str(e)}")

    # 补充电影详情
    items = _enrich_movie_details(recommendations)

    return {
        "algorithm": algo_name,
        "algorithm_display_name": algo_class.display_name,
        "cold_start": len(items) == 0,
        "items": items,
        "total": len(items),
    }


@router.get("/explain", summary="推荐结果解释")
def explain_recommendation(
    target_mid: str = Query(..., description="目标推荐电影 ID"),
    algorithm: Optional[str] = Query("kg_path", description="推荐算法"),
    user=Depends(get_current_user),
):
    """
    为指定电影生成推荐解释（简化版，返回基本推理路径）
    """
    algo_name = (algorithm or "kg_path").lower()

    # 获取目标电影基本信息
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT douban_id, name, douban_score, year, cover, genres "
                "FROM movies WHERE douban_id = %s",
                (target_mid,),
            )
            movie = cursor.fetchone()
    finally:
        conn.close()

    if not movie:
        return {
            "algorithm": algo_name,
            "target_movie": {"mid": target_mid},
            "reason_paths": [],
            "meta": {"has_graph_evidence": False, "cold_start": True},
        }

    genres = [g.strip() for g in (movie.get("genres") or "").split("/") if g.strip()]
    target_movie = {
        "mid": target_mid,
        "title": movie["name"],
        "rating": float(movie["douban_score"]) if movie.get("douban_score") else None,
        "year": movie.get("year"),
        "cover": movie.get("cover"),
        "genres": genres,
    }
    positive_movies = _load_positive_movies_for_user(user["id"], algo_name)
    explain_payload = _build_recommendation_explain_payload(
        target_movie=target_movie,
        positive_movies=positive_movies,
    )
    reason_paths = explain_payload["reason_paths"]
    matched_entities = explain_payload["matched_entities"]
    nodes = explain_payload["nodes"]
    edges = explain_payload["edges"]

    return {
        "algorithm": algo_name,
        "target_movie": target_movie,
        "reason_paths": reason_paths,
        "matched_entities": matched_entities,
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "has_graph_evidence": bool(nodes and edges),
            "cold_start": False,
        },
    }


@router.get("/algorithms", summary="可用推荐算法列表")
async def list_algorithms():
    """返回所有可用的推荐算法"""
    return {
        "algorithms": [
            {
                "name": name,
                "display_name": cls.display_name,
                "type": "KG" if name.startswith("kg_") else "基线",
            }
            for name, cls in ALGORITHMS.items()
        ]
    }


@router.get("/evaluate", summary="离线评估报告")
async def get_evaluation_report(user=Depends(get_current_user)):
    """
    返回最新的离线评估报告

    优先读取 reports/eval_results.json；若主报告不存在，则回退到 history 中最新的一份。
    """
    import json
    import os

    reports_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "reports",
    )
    json_path = os.path.join(reports_dir, "eval_results.json")
    history_dir = os.path.join(reports_dir, "history")

    # 优先返回已有报告
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    history_candidates = sorted(
        [
            path
            for path in glob.glob(os.path.join(history_dir, "*.json"))
            if not path.endswith("_legacy.json")
        ],
        key=os.path.getmtime,
        reverse=True,
    )
    if history_candidates:
        with open(history_candidates[0], "r", encoding="utf-8") as f:
            payload = json.load(f)
        payload["report_source"] = os.path.basename(history_candidates[0])
        return payload

    # 没有报告，提示用户运行评估脚本
    return {
        "message": "评估报告尚未生成，请在终端运行: python -m app.algorithms.evaluator",
        "results": None,
    }


def _enrich_movie_details(recommendations: list[dict]) -> list[dict]:
    """批量补充电影详情"""
    if not recommendations:
        return []

    mids = [r["mid"] for r in recommendations]
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            placeholders = ", ".join(["%s"] * len(mids))
            cursor.execute(
                f"SELECT douban_id, name, douban_score, year, cover, genres "
                f"FROM movies WHERE douban_id IN ({placeholders})",
                mids,
            )
            movies_map = {}
            for row in cursor.fetchall():
                mid = str(row["douban_id"])
                genres = [g.strip() for g in (row.get("genres") or "").split("/") if g.strip()]
                movies_map[mid] = {
                    "mid": mid,
                    "title": row["name"],
                    "rating": float(row["douban_score"]) if row.get("douban_score") else None,
                    "year": row.get("year"),
                    "cover": row.get("cover"),
                    "genres": genres,
                }
    finally:
        conn.close()

    items = []
    for rec in recommendations:
        movie_info = movies_map.get(rec["mid"])
        if not movie_info:
            continue
        items.append({
            "movie": movie_info,
            "score": rec["score"],
            "reasons": [rec.get("reason", "")],
            "source_algorithms": [rec.get("source", "")],
        })

    return items
