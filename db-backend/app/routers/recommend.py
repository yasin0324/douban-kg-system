from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user

REMOVAL_MESSAGE = "recommendation backend removed"
EMPTY_PROFILE_SUMMARY = {
    "rating_count": 0,
    "strong_positive_ratings": 0,
    "weak_positive_ratings": 0,
    "weak_negative_ratings": 0,
    "likes": 0,
    "wants": 0,
    "positive_movie_count": 0,
    "behavior_movie_count": 0,
    "cold_start": True,
}

router = APIRouter(prefix="/api/recommend", tags=["遗留兼容接口"])


def _normalize_algorithm(algorithm: str | None) -> str:
    return (algorithm or "cfkg").lower()


@router.get("/personal", summary="个人电影推荐")
async def get_personal_recommendations(
    algorithm: Optional[str] = Query(
        "cfkg",
        description="推荐算法类型: cfkg, ppr, content, cf, hybrid, itemcf, tfidf",
    ),
    limit: int = Query(20, ge=1, le=50),
    exclude_movie_ids: Optional[List[str]] = Query(
        None,
        description="重新生成时希望尽量避开的电影",
    ),
    reroll_token: Optional[str] = Query(None, description="重新生成请求的随机标识"),
    user=Depends(get_current_user),
):
    del limit, exclude_movie_ids, reroll_token, user
    return {
        "algorithm": _normalize_algorithm(algorithm),
        "cold_start": True,
        "generation_mode": "disabled",
        "profile_summary": dict(EMPTY_PROFILE_SUMMARY),
        "profile_highlights": [],
        "items": [],
        "disabled": True,
        "message": REMOVAL_MESSAGE,
    }


@router.get("/explain", summary="推荐结果解释图")
def explain_recommendation(
    target_mid: str = Query(..., description="目标推荐电影 ID"),
    algorithm: Optional[str] = Query(
        "cfkg",
        description="推荐算法类型: cfkg, ppr, content, cf, hybrid, itemcf, tfidf",
    ),
    user=Depends(get_current_user),
):
    del user
    return {
        "algorithm": _normalize_algorithm(algorithm),
        "target_movie": {
            "mid": target_mid,
            "title": "",
            "rating": None,
            "year": None,
            "cover": None,
            "genres": [],
        },
        "representative_movies": [],
        "profile_highlights": [],
        "profile_reasons": [],
        "negative_signals": [],
        "nodes": [],
        "edges": [],
        "reason_paths": [],
        "matched_entities": [],
        "meta": {
            "has_graph_evidence": False,
            "representative_movie_count": 0,
            "cold_start": True,
        },
        "disabled": True,
        "message": REMOVAL_MESSAGE,
    }
