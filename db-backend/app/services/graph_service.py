"""
图谱探索服务 — 以电影/影人为中心的子图查询、最短路径、共同电影
"""
import time

ALLOWED_REL_TYPES = {
    "DIRECTED",
    "ACTED_IN",
    "HAS_GENRE",
    "IN_REGION",
    "IN_LANGUAGE",
    "HAS_CONTENT_TYPE",
    "IN_YEAR_BUCKET",
}


def _safe_run(session, query: str, timeout_ms: int | None = None, **params):
    """优先使用事务超时，驱动不支持时回退到普通查询。捕获超时等异常返回空列表。"""
    try:
        if timeout_ms:
            timeout_seconds = max(timeout_ms, 100) / 1000
            try:
                with session.begin_transaction(timeout=timeout_seconds) as tx:
                    return list(tx.run(query, **params))
            except TypeError:
                pass
        return list(session.run(query, **params))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"图谱查询异常: {e}")
        return []


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
    timeout_ms = min(max(timeout_ms, 100), 10000)
    if depth == 2 and timeout_ms < 5000:
        timeout_ms = 5000

    start_time = time.time()

    # 使用分步查询避免路径爆炸
    query = f"""
    MATCH (m:Movie {{mid: $mid}})
    OPTIONAL MATCH (m)-[r1]-(n1)
    WHERE (n1:Movie OR n1:Person OR n1:Genre)
      AND type(r1) IN ['DIRECTED', 'ACTED_IN', 'HAS_GENRE']
    WITH m, collect(DISTINCT {{node: n1, rel: r1}})[..{node_limit}] AS hop1
    UNWIND hop1 AS h1
    WITH m, h1.node AS n1, h1.rel AS r1, hop1
    """ + (f"""
    OPTIONAL MATCH (n1)-[r2]-(n2)
    WHERE (n2:Movie OR n2:Person OR n2:Genre)
      AND type(r2) IN ['DIRECTED', 'ACTED_IN', 'HAS_GENRE']
      AND n2 <> m
    WITH m, n1, r1, collect(DISTINCT {{node: n2, rel: r2}})[..10] AS hop2
    RETURN m, collect(DISTINCT {{node: n1, rel: r1}}) AS edges1,
           reduce(acc = [], h2 IN collect(hop2) | acc + h2) AS edges2
    """ if depth == 2 else """
    RETURN m, collect(DISTINCT {node: n1, rel: r1}) AS edges1, [] AS edges2
    """)

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

    # 处理 1 跳
    for item in record.get("edges1", []):
        node = item.get("node") if item else None
        rel = item.get("rel") if item else None
        if node is None or rel is None:
            continue
        node_payload = _to_node_payload(node)
        if not node_payload:
            continue
        nid, npayload = node_payload
        nodes_map[nid] = npayload
        # 提取关系
        rel_type = getattr(rel, "type", None)
        if rel_type and rel_type in ALLOWED_REL_TYPES:
            start_node = getattr(rel, "start_node", None)
            end_node = getattr(rel, "end_node", None)
            sp = _to_node_payload(start_node) if start_node and hasattr(start_node, "labels") else None
            ep = _to_node_payload(end_node) if end_node and hasattr(end_node, "labels") else None
            if sp and ep:
                edges_set.add((sp[0], ep[0], rel_type))
            elif center_payload:
                edges_set.add((center_payload[0], nid, rel_type))

    # 处理 2 跳
    for item in record.get("edges2", []):
        node = item.get("node") if item else None
        rel = item.get("rel") if item else None
        if node is None or rel is None:
            continue
        node_payload = _to_node_payload(node)
        if not node_payload:
            continue
        nid, npayload = node_payload
        nodes_map[nid] = npayload
        rel_type = getattr(rel, "type", None)
        if rel_type and rel_type in ALLOWED_REL_TYPES:
            start_node = getattr(rel, "start_node", None)
            end_node = getattr(rel, "end_node", None)
            sp = _to_node_payload(start_node) if start_node and hasattr(start_node, "labels") else None
            ep = _to_node_payload(end_node) if end_node and hasattr(end_node, "labels") else None
            if sp and ep:
                edges_set.add((sp[0], ep[0], rel_type))

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
    timeout_ms = min(max(timeout_ms, 100), 10000)
    if depth == 2 and timeout_ms < 5000:
        timeout_ms = 5000

    start_time = time.time()

    query = f"""
    MATCH (p:Person {{pid: $pid}})
    OPTIONAL MATCH (p)-[r1]-(n1)
    WHERE (n1:Movie OR n1:Person OR n1:Genre)
      AND type(r1) IN ['DIRECTED', 'ACTED_IN', 'HAS_GENRE']
    WITH p, collect(DISTINCT {{node: n1, rel: r1}})[..{node_limit}] AS hop1
    UNWIND hop1 AS h1
    WITH p, h1.node AS n1, h1.rel AS r1, hop1
    """ + (f"""
    OPTIONAL MATCH (n1)-[r2]-(n2)
    WHERE (n2:Movie OR n2:Person OR n2:Genre)
      AND type(r2) IN ['DIRECTED', 'ACTED_IN', 'HAS_GENRE']
      AND n2 <> p
    WITH p, n1, r1, collect(DISTINCT {{node: n2, rel: r2}})[..10] AS hop2
    RETURN p, collect(DISTINCT {{node: n1, rel: r1}}) AS edges1,
           reduce(acc = [], h2 IN collect(hop2) | acc + h2) AS edges2
    """ if depth == 2 else """
    RETURN p, collect(DISTINCT {node: n1, rel: r1}) AS edges1, [] AS edges2
    """)

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

    # 处理 1 跳
    for item in record.get("edges1", []):
        node = item.get("node") if item else None
        rel = item.get("rel") if item else None
        if node is None or rel is None:
            continue
        node_payload = _to_node_payload(node)
        if not node_payload:
            continue
        nid, npayload = node_payload
        nodes_map[nid] = npayload
        rel_type = getattr(rel, "type", None)
        if rel_type and rel_type in ALLOWED_REL_TYPES:
            start_node = getattr(rel, "start_node", None)
            end_node = getattr(rel, "end_node", None)
            sp = _to_node_payload(start_node) if start_node and hasattr(start_node, "labels") else None
            ep = _to_node_payload(end_node) if end_node and hasattr(end_node, "labels") else None
            if sp and ep:
                edges_set.add((sp[0], ep[0], rel_type))
            elif center_payload:
                edges_set.add((center_payload[0], nid, rel_type))

    # 处理 2 跳
    for item in record.get("edges2", []):
        node = item.get("node") if item else None
        rel = item.get("rel") if item else None
        if node is None or rel is None:
            continue
        node_payload = _to_node_payload(node)
        if not node_payload:
            continue
        nid, npayload = node_payload
        nodes_map[nid] = npayload
        rel_type = getattr(rel, "type", None)
        if rel_type and rel_type in ALLOWED_REL_TYPES:
            start_node = getattr(rel, "start_node", None)
            end_node = getattr(rel, "end_node", None)
            sp = _to_node_payload(start_node) if start_node and hasattr(start_node, "labels") else None
            ep = _to_node_payload(end_node) if end_node and hasattr(end_node, "labels") else None
            if sp and ep:
                edges_set.add((sp[0], ep[0], rel_type))

    return _finalize_graph(nodes_map, edges_set, depth, start_time, node_limit, edge_limit)


def find_shortest_path(session, from_id: str, to_id: str, max_hops: int = 6, exclude_genre: bool = False) -> dict:
    """查找两个实体之间的最短路径"""
    max_hops = min(max(max_hops, 1), 6)
    start_time = time.time()

    if exclude_genre:
        # 排除 HAS_GENRE 关系，只通过演职人员关系查找路径
        cypher = f"""
        MATCH (start), (end)
        WHERE (start.mid = $from_id OR start.pid = $from_id OR start.name = $from_id)
          AND (end.mid = $to_id OR end.pid = $to_id OR end.name = $to_id)
        MATCH path = shortestPath((start)-[:DIRECTED|ACTED_IN*..{max_hops}]-(end))
        RETURN path
        LIMIT 1
        """
    else:
        cypher = f"""
        MATCH (start), (end)
        WHERE (start.mid = $from_id OR start.pid = $from_id OR start.name = $from_id)
          AND (end.mid = $to_id OR end.pid = $to_id OR end.name = $to_id)
        MATCH path = shortestPath((start)-[*..{max_hops}]-(end))
        RETURN path
        LIMIT 1
        """

    result = session.run(
        cypher,
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
        RETURN DISTINCT m.mid AS mid, m.title AS title, m.rating AS rating, m.year AS year
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
