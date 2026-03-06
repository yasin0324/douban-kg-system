"""
图原生内容推荐算法 (Graph-Content-Based)
"""
from typing import List, Dict, Any
from app.db.neo4j import Neo4jConnection

async def get_graph_content_recommendations(user_id: int, seed_movie_ids: List[str], limit: int = 50) -> List[Dict[str, Any]]:
    """
    通过 Neo4j 图谱中的共享实体路径找相似电影。
    寻找与目标电影共享最多导演(Director)、核心演员(Actor)、编剧(Writer)和流派(Genre)的其他电影。
    """
    if not seed_movie_ids:
        return []

    driver = Neo4jConnection.get_driver()
    
    # 查找跟 seed_movie_ids 有共享节点的最相似电影
    query = """
    MATCH (source:Movie)-[:DIRECTED|HAS_GENRE|ACTED_IN]-(shared_node)-[:DIRECTED|HAS_GENRE|ACTED_IN]-(target:Movie)
    WHERE source.mid IN $seed_ids AND NOT target.mid IN $seed_ids
    OPTIONAL MATCH (u:User {id: $user_id})-[:RATED]->(target)
    WITH target, shared_node, u
    WHERE u IS NULL // 排除已看过的
    WITH target, count(DISTINCT shared_node) AS shared_count, collect(DISTINCT shared_node.name) AS shared_reasons
    RETURN target.mid AS movie_id, target.title AS title, shared_count, shared_reasons
    ORDER BY shared_count DESC
    LIMIT $limit
    """
    
    results = []
    
    # 因为使用 async，这里虽然 driver.session() 是阻塞的，但由于 Neo4j 端计算很快，暂用同步包在 async 中。
    # 或可用 run_in_executor 优化，这里为了保持实现清晰，直接调用。
    with driver.session() as session:
        records = session.run(query, seed_ids=seed_movie_ids, user_id=user_id, limit=limit)
        for record in records:
            reasons = record["shared_reasons"]
            # 格式化推荐理由
            reason_text = ""
            if len(reasons) > 0:
                short_reasons = reasons[:3]
                reason_text = f"含有共性特征: {', '.join(short_reasons)}"
                if len(reasons) > 3:
                    reason_text += f" 等 {len(reasons)} 个共同点"
                    
            results.append({
                "movie_id": record["movie_id"],
                "score": float(record["shared_count"]), # Raw score, 将由 hybrid_manager 归一化
                "reasons": [reason_text] if reason_text else [],
                "source": "graph_content"
            })
            
    return results
