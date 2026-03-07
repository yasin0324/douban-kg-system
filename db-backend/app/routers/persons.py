"""
影人路由 — /api/persons
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_mysql_conn, get_neo4j_session
from app.services import person_service

router = APIRouter(prefix="/api/persons", tags=["影人"])


@router.get("/search", summary="搜索影人")
def search(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    conn=Depends(get_mysql_conn),
):
    return person_service.search_persons(conn, q, page, size)


@router.get("/{pid}", summary="影人详情")
def detail(pid: str, session=Depends(get_neo4j_session)):
    result = person_service.get_person_detail(session, pid)
    if not result:
        raise HTTPException(status_code=404, detail="影人不存在")
    return result


@router.get("/{pid}/movies", summary="影人参演/执导电影")
def person_movies(pid: str, session=Depends(get_neo4j_session)):
    result = person_service.get_person_movies(session, pid)
    if not result:
        raise HTTPException(status_code=404, detail="影人不存在")
    return result


@router.get("/{pid}/collaborators", summary="合作者")
def collaborators(pid: str, limit: int = Query(10, ge=1, le=50), session=Depends(get_neo4j_session)):
    return person_service.get_collaborators(session, pid, limit)
