"""
图谱探索服务 — 以电影/影人为中心的子图查询、最短路径、共同电影
"""
import time

ALLOWED_REL_TYPES = {"DIRECTED", "ACTED_IN", "HAS_GENRE"}


def _safe_run(session, query: str, timeout_ms: int | None = None, **params):
    """优先使用事务超时，驱动不支持时回退到普通查询。"""
    if timeout_ms:
        timeout_seconds = max(timeout_ms, 100) / 1000
        try:
            with session.begin_transaction(timeout=timeout_seconds) as tx:
                return list(tx.run(query, **params))
        except TypeError:
            pass
    return list(session.run(query, **params))


def _to_node_payload(node):
    if node is None:
        return None
    labels = list(node.labels)
    node_type = labels[0] if labels else "Unknown"
    props = dict(node)
    node_id_val = props.get("mid") or props.get("pid") or props.get("name")
    if not node_id_val:
        return None

    node_id = f"{node_type.lower()}_{node_id_val}"
    label = props.get("title") or props.get("name") or str(node_id_val)
    node_props = None
    if node_type == "Movie":
        node_props = {k: v for k, v in props.items() if k in ("rating", "year", "cover")}
    elif node_type == "Person":
        node_props = {k: v for k, v in props.items() if k in ("profession", "sex")}
    if node_props == {}:
        node_props = None
    return node_id, {"id": node_id, "label": label, "type": node_type, "properties": node_props}


def _add_path_to_graph(path, nodes_map: dict, edges_set: set):
    if path is None:
        return
    path_nodes = list(path.nodes)
    for node in path_nodes:
        node_payload = _to_node_payload(node)
        if node_payload:
            node_id, payload = node_payload
            nodes_map[node_id] = payload

    for idx, rel in enumerate(path.relationships):
        rel_type = getattr(rel, "type", None)
        if not rel_type:
            continue
        if rel_type not in ALLOWED_REL_TYPES:
            continue

        start_node = getattr(rel, "start_node", None)
        end_node = getattr(rel, "end_node", None)
        if not hasattr(start_node, "labels") or not hasattr(end_node, "labels"):
            if idx + 1 >= len(path_nodes):
                continue
            start_node = path_nodes[idx]
            end_node = path_nodes[idx + 1]

        start_payload = _to_node_payload(start_node)
        end_payload = _to_node_payload(end_node)
        if not start_payload or not end_payload:
            continue
        source = start_payload[0]
        target = end_payload[0]
        edges_set.add((source, target, rel_type))


def _finalize_graph(nodes_map: dict, edges_set: set, depth: int, start_time: float, node_limit: int, edge_limit: int) -> dict:
    nodes = list(nodes_map.values())
    edges = [{"source": s, "target": t, "type": rel_type} for s, t, rel_type in sorted(edges_set)]
    truncated = len(nodes) > node_limit or len(edges) > edge_limit
    query_time = int((time.time() - start_time) * 1000)
    return {
        "nodes": nodes[:node_limit],
        "edges": edges[:edge_limit],
        "meta": {
            "depth": depth,
            "node_count": min(len(nodes), node_limit),
            "edge_count": min(len(edges), edge_limit),
            "truncated": truncated,
            "query_time_ms": query_time,
        },
    }


def _empty_graph(depth: int, start_time: float) -> dict:
    query_time = int((time.time() - start_time) * 1000)
    return {
        "nodes": [],
        "edges": [],
        "meta": {
            "depth": depth,
            "node_count": 0,
            "edge_count": 0,
            "truncated": False,
            "query_time_ms": query_time,
        },
    }


def get_movie_graph(
    session,
    mid: str,
    depth: int = 1,
    node_limit: int = 150,
    edge_limit: int = 300,
    timeout_ms: int = 1200,
) -> dict:
    """以电影为中心展开 N 跳关联图"""
    depth = min(max(depth, 1), 2)
    node_limit = min(max(node_limit, 1), 500)
    edge_limit = min(max(edge_limit, 1), 1000)
    timeout_ms = min(max(timeout_ms, 100), 3000)

    start_time = time.time()
    query = f"""
    MATCH (m:Movie {{mid: $mid}})
    OPTIONAL MATCH path = (m)-[*1..{depth}]-(n)
    WHERE (n:Movie OR n:Person OR n:Genre)
      AND ALL(rel IN relationships(path) WHERE type(rel) IN ['DIRECTED', 'ACTED_IN', 'HAS_GENRE'])
    WITH m, [p IN collect(DISTINCT path) WHERE p IS NOT NULL] AS paths
    RETURN m, paths
    """
    records = _safe_run(session, query, timeout_ms=timeout_ms, mid=mid)
    if not records:
        return _empty_graph(depth, start_time)

    record = records[0]
    if record.get("m") is None:
        return _empty_graph(depth, start_time)

    nodes_map: dict = {}
    edges_set: set = set()

    center_payload = _to_node_payload(record["m"])
    if center_payload:
        center_id, center_node = center_payload
        nodes_map[center_id] = center_node

    for path in record.get("paths", []):
        _add_path_to_graph(path, nodes_map, edges_set)

    return _finalize_graph(nodes_map, edges_set, depth, start_time, node_limit, edge_limit)


def get_person_graph(
    session,
    pid: str,
    depth: int = 1,
    node_limit: int = 150,
    edge_limit: int = 300,
    timeout_ms: int = 1200,
) -> dict:
    """以影人为中心展开 N 跳关联图"""
    depth = min(max(depth, 1), 2)
    node_limit = min(max(node_limit, 1), 500)
    edge_limit = min(max(edge_limit, 1), 1000)
    timeout_ms = min(max(timeout_ms, 100), 3000)

    start_time = time.time()
    query = f"""
    MATCH (p:Person {{pid: $pid}})
    OPTIONAL MATCH path = (p)-[*1..{depth}]-(n)
    WHERE (n:Movie OR n:Person OR n:Genre)
      AND ALL(rel IN relationships(path) WHERE type(rel) IN ['DIRECTED', 'ACTED_IN', 'HAS_GENRE'])
    WITH p, [p0 IN collect(DISTINCT path) WHERE p0 IS NOT NULL] AS paths
    RETURN p, paths
    """
    records = _safe_run(session, query, timeout_ms=timeout_ms, pid=pid)
    if not records:
        return _empty_graph(depth, start_time)

    record = records[0]
    if record.get("p") is None:
        return _empty_graph(depth, start_time)

    nodes_map: dict = {}
    edges_set: set = set()

    center_payload = _to_node_payload(record["p"])
    if center_payload:
        center_id, center_node = center_payload
        nodes_map[center_id] = center_node

    for path in record.get("paths", []):
        _add_path_to_graph(path, nodes_map, edges_set)

    return _finalize_graph(nodes_map, edges_set, depth, start_time, node_limit, edge_limit)


def find_shortest_path(session, from_id: str, to_id: str, max_hops: int = 6) -> dict:
    """查找两个实体之间的最短路径"""
    max_hops = min(max(max_hops, 1), 6)
    start_time = time.time()

    result = session.run(
        f"""
        MATCH (start), (end)
        WHERE (start.mid = $from_id OR start.pid = $from_id OR start.name = $from_id)
          AND (end.mid = $to_id OR end.pid = $to_id OR end.name = $to_id)
        MATCH path = shortestPath((start)-[*..{max_hops}]-(end))
        RETURN path
        LIMIT 1
        """,
        from_id=from_id,
        to_id=to_id,
    )
    record = result.single()
    if not record:
        return _empty_graph(0, start_time)

    path = record["path"]
    nodes_map: dict = {}
    edges_set: set = set()
    _add_path_to_graph(path, nodes_map, edges_set)

    query_time = int((time.time() - start_time) * 1000)
    edges = [{"source": s, "target": t, "type": rel_type} for s, t, rel_type in sorted(edges_set)]
    return {
        "nodes": list(nodes_map.values()),
        "edges": edges,
        "meta": {
            "depth": len(path.relationships),
            "node_count": len(nodes_map),
            "edge_count": len(edges),
            "truncated": False,
            "query_time_ms": query_time,
        },
    }


def find_common_movies(session, pid1: str, pid2: str, limit: int = 50) -> dict:
    """查找两位影人的共同电影"""
    start_time = time.time()
    result = session.run(
        """
        MATCH (p1:Person {pid: $pid1})-[:DIRECTED|ACTED_IN]->(m:Movie)<-[:DIRECTED|ACTED_IN]-(p2:Person {pid: $pid2})
        RETURN m.mid AS mid, m.title AS title, m.rating AS rating, m.year AS year
        ORDER BY m.year DESC
        LIMIT $limit
        """,
        pid1=pid1,
        pid2=pid2,
        limit=limit,
    )
    movies = [dict(r) for r in result]
    query_time = int((time.time() - start_time) * 1000)
    return {"movies": movies, "count": len(movies), "query_time_ms": query_time}
