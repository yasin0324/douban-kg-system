"""
基于图拓扑的协同过滤 (Graph-Collaborative-Filtering)
"""
from typing import List, Dict, Any
from app.db.neo4j import Neo4jConnection

async def get_graph_cf_recommendations(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """
    查找同样喜欢（打过高分）种子电影的相似用户，并抓取他们给出好评的其他未看电影。
    """
    driver = Neo4jConnection.get_driver()
    
    # 查找相似用户 (给同样电影打 >= 4 星的视为品味相似)
    query = """
    MATCH (u1:User {id: $user_id})-[:RATED]->(m:Movie)<-[:RATED]-(u2:User)
    // 可以加更细粒度的条件比如 u1 的打分和 u2 的打分都较高
    WITH u1, u2, count(m) AS similarity
    ORDER BY similarity DESC LIMIT 20
    
    // 从这些最相似的20个用户中，寻找他们打过高分的电影 (>=4星)
    MATCH (u2)-[r:RATED]->(rec:Movie)
    WHERE r.rating >= 4 AND NOT (u1)-[:RATED]->(rec)
    WITH rec, sum(r.rating * similarity) AS cf_score, count(u2) AS similar_user_count
    RETURN rec.mid AS movie_id, rec.title AS title, cf_score, similar_user_count
    ORDER BY cf_score DESC 
    LIMIT $limit
    """
    
    results = []
    
    with driver.session() as session:
        records = session.run(query, user_id=user_id, limit=limit)
        for record in records:
            user_count = record["similar_user_count"]
            results.append({
                "movie_id": record["movie_id"],
                "score": float(record["cf_score"]), 
                "reasons": [f"有 {user_count} 位与您品味相似的用户给它打了高分"],
                "source": "graph_cf"
            })
            
    return results
