"""
隐性关系挖掘 (Personalized PageRank)
"""
from typing import List, Dict, Any
import logging
from app.db.neo4j import Neo4jConnection

logger = logging.getLogger(__name__)

async def get_graph_ppr_recommendations(user_id: int, seed_movie_ids: List[str], limit: int = 50) -> List[Dict[str, Any]]:
    """
    基于 Neo4j 图库计算 Personalized PageRank (PPR)。
    从用户偏好的节点(种子节点)出发，跳出直接关联，挖掘深层隐性相关节点。
    
    依赖: Neo4j GDS 插件。
    若未安装 GDS，返回空列表供降级。
    """
    if not seed_movie_ids:
        return []

    driver = Neo4jConnection.get_driver()
    
    # 我们需要先根据 mid 查出内部节点 ID，传递给 GDS
    get_node_ids_query = """
    MATCH (m:Movie) WHERE m.mid IN $seed_ids
    RETURN id(m) AS internal_id
    """
    
    import uuid
    graph_name = f"ppr_graph_{uuid.uuid4().hex[:8]}"
    
    project_query = f"""
    CALL gds.graph.project(
      '{graph_name}',
      ['Movie', 'Person', 'Genre'],
      ['ACTED_IN', 'DIRECTED', 'HAS_GENRE']
    )
    """
    
    ppr_query = f"""
    CALL gds.pageRank.stream('{graph_name}', {{
      sourceNodes: $source_nodes,
      dampingFactor: 0.85,
      maxIterations: 20
    }})
    YIELD nodeId, score
    WITH gds.util.asNode(nodeId) AS n, score
    WHERE 'Movie' IN labels(n) AND NOT n.mid IN $seed_ids
    OPTIONAL MATCH (u:User {{id: $user_id}})-[:RATED]->(n)
    WITH n, score, u
    WHERE u IS NULL // 排除看过的
    RETURN n.mid AS movie_id, n.title AS title, score AS ppr_score
    ORDER BY ppr_score DESC
    LIMIT $limit
    """
    
    drop_query = f"CALL gds.graph.drop('{graph_name}', false)"
    
    results = []
    
    with driver.session() as session:
        try:
            # 1. 查找 source node 内部 ID
            node_ids_res = session.run(get_node_ids_query, seed_ids=seed_movie_ids)
            source_nodes = [record["internal_id"] for record in node_ids_res]
            
            if not source_nodes:
                return []
                
            # 2. 投射独立图
            session.run(project_query)
            
            # 3. 执行 PPR
            records = session.run(ppr_query, source_nodes=source_nodes, seed_ids=seed_movie_ids, user_id=user_id, limit=limit)
            for record in records:
                results.append({
                    "movie_id": record["movie_id"],
                    "score": float(record["ppr_score"]),
                    "reasons": ["通过深层图节点游走发掘的隐秘关联"],
                    "source": "graph_ppr"
                })
        except Exception as e:
            logger.warning(f"Neo4j GDS 算法执行失败，通常是因为未安装 GDS 插件：{e}")
            return []
        finally:
            # 确保无论成功失败都会清理图内存
            try:
                session.run(drop_query)
            except Exception:
                pass
            
    return results
