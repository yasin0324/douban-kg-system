"""
图谱路由 — /api/graph
"""
from fastapi import APIRouter, Depends, Query

from app.dependencies import get_neo4j_session
from app.services import graph_service

router = APIRouter(prefix="/api/graph", tags=["图谱探索"])


@router.get("/movie/{mid}", summary="电影关联图")
def movie_graph(
    mid: str,
    depth: int = Query(1, ge=1, le=2),
    node_limit: int = Query(150, ge=1, le=500),
    edge_limit: int = Query(300, ge=1, le=1000),
    timeout_ms: int = Query(1200, ge=100, le=10000),
    session=Depends(get_neo4j_session),
):
    return graph_service.get_movie_graph(session, mid, depth, node_limit, edge_limit, timeout_ms)


@router.get("/person/{pid}", summary="影人关联图")
def person_graph(
    pid: str,
    depth: int = Query(1, ge=1, le=2),
    node_limit: int = Query(150, ge=1, le=500),
    edge_limit: int = Query(300, ge=1, le=1000),
    timeout_ms: int = Query(1200, ge=100, le=10000),
    session=Depends(get_neo4j_session),
):
    return graph_service.get_person_graph(session, pid, depth, node_limit, edge_limit, timeout_ms)


@router.get("/path", summary="最短路径")
def shortest_path(
    from_id: str = Query(..., alias="from"),
    to_id: str = Query(..., alias="to"),
    max_hops: int = Query(6, ge=1, le=6),
    session=Depends(get_neo4j_session),
):
    return graph_service.find_shortest_path(session, from_id, to_id, max_hops)


@router.get("/common", summary="共同电影")
def common_movies(
    person1: str = Query(...),
    person2: str = Query(...),
    limit: int = Query(50, ge=1, le=100),
    session=Depends(get_neo4j_session),
):
    return graph_service.find_common_movies(session, person1, person2, limit)
