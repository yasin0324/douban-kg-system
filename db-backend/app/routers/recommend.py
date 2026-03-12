"""
推荐系统路由 — 个性化推荐、推荐解释、离线评估
"""

import asyncio
import glob
import logging
from functools import partial
from threading import BoundedSemaphore, Lock
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.algorithms import ALGORITHMS, ALGORITHM_NAMES
from app.config import settings
from app.db.mysql import get_connection
from app.db.neo4j import Neo4jConnection
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

    # 如果是 KG 算法，尝试获取图路径证据
    reason_paths = []
    nodes = []
    edges = []

    if algo_name.startswith("kg_"):
        driver = Neo4jConnection.get_driver()
        with driver.session() as session:
            # 查询电影关联的导演和演员
            result = session.run(
                "MATCH (m:Movie {mid: $mid})<-[:DIRECTED]-(d:Person) "
                "RETURN d.name AS name, 'director' AS role LIMIT 3 "
                "UNION ALL "
                "MATCH (m:Movie {mid: $mid})<-[:ACTED_IN]-(a:Person) "
                "RETURN a.name AS name, 'actor' AS role LIMIT 5",
                mid=target_mid,
            )
            related_persons = [{"name": r["name"], "role": r["role"]} for r in result]

            for person in related_persons:
                role_label = "导演" if person["role"] == "director" else "演员"
                reason_paths.append({
                    "relation_label": f"共同{role_label}",
                    "matched_entities": [person["name"]],
                })

    return {
        "algorithm": algo_name,
        "target_movie": {
            "mid": target_mid,
            "title": movie["name"],
            "rating": float(movie["douban_score"]) if movie.get("douban_score") else None,
            "year": movie.get("year"),
            "cover": movie.get("cover"),
            "genres": genres,
        },
        "reason_paths": reason_paths,
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "has_graph_evidence": len(reason_paths) > 0,
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
