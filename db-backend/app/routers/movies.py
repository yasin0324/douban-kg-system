"""
电影路由 — /api/movies
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_mysql_conn, get_neo4j_session
from app.services import movie_service

router = APIRouter(prefix="/api/movies", tags=["电影"])


@router.get("/search", summary="搜索电影")
def search(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    conn=Depends(get_mysql_conn),
):
    return movie_service.search_movies(conn, q, page, size)


@router.get("/genres", summary="获取所有类型")
def genres(session=Depends(get_neo4j_session)):
    return movie_service.get_genres(session)


@router.get("/top", summary="高分排行")
def top(
    genre: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    session=Depends(get_neo4j_session),
):
    return movie_service.get_top_movies(session, genre, limit)


@router.get("/filter", summary="多条件筛选")
def filter_movies(
    genre: str = Query(None),
    year_from: int = Query(None),
    year_to: int = Query(None),
    rating_min: float = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session=Depends(get_neo4j_session),
):
    return movie_service.filter_movies(session, genre, year_from, year_to, rating_min, page, size)


@router.get("/{mid}", summary="电影详情")
def detail(mid: str, session=Depends(get_neo4j_session)):
    result = movie_service.get_movie_detail(session, mid)
    if not result:
        raise HTTPException(status_code=404, detail="电影不存在")
    return result


@router.get("/{mid}/credits", summary="演职人员")
def credits(mid: str, session=Depends(get_neo4j_session)):
    result = movie_service.get_movie_credits(session, mid)
    if not result:
        raise HTTPException(status_code=404, detail="电影不存在")
    return result
