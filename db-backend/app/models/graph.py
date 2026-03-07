"""
图谱相关 Pydantic 模型
"""
from typing import Optional, List, Any, Dict
from pydantic import BaseModel


class GraphNode(BaseModel):
    id: str
    label: str
    type: str  # Movie / Person / Genre
    properties: Optional[Dict[str, Any]] = None


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str  # DIRECTED / ACTED_IN / HAS_GENRE


class GraphMeta(BaseModel):
    depth: int = 1
    node_count: int = 0
    edge_count: int = 0
    truncated: bool = False
    query_time_ms: Optional[int] = None


class GraphResponse(BaseModel):
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
    meta: GraphMeta = GraphMeta()
