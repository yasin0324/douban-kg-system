"""
电影查询服务
"""
from typing import Optional, List


# ---------- MySQL 搜索 ----------

def search_movies(conn, q: str, page: int = 1, size: int = 20) -> dict:
    """多关键词与精准回退搜索电影（MySQL LIKE）"""
    import re
    import jieba
    offset = (page - 1) * size
    
    with conn.cursor() as cursor:
        # 第一步：尝试精准 LIKE 匹配 (应对用户刚好少打一个冒号的情况，或者完整片名)
        like_q = f"%{q}%"
        cursor.execute(
            "SELECT COUNT(*) as total FROM movies WHERE name LIKE %s OR alias LIKE %s",
            (like_q, like_q),
        )
        total = cursor.fetchone()["total"]
        
        if total > 0:
            cursor.execute(
                "SELECT douban_id as mid, name as title, douban_score as rating, year, cover, genres "
                "FROM movies WHERE name LIKE %s OR alias LIKE %s "
                "ORDER BY douban_score DESC LIMIT %s OFFSET %s",
                (like_q, like_q, size, offset),
            )
            items = cursor.fetchall()
        else:
            # 第二步：精准匹配失败，启动 NLP 分词模糊匹配
            # 把用户输入中的大部分特殊符号替换为空格
            clean_q = re.sub(r'[^\w\u4e00-\u9fa5]+', ' ', q).strip()
            # 使用 jieba 搜索引擎模式分词，提取细粒度词汇
            keywords = list(jieba.cut_for_search(clean_q))
            # 去除空字符串和单字（如果不需要全分单字的话），或者直接不过滤单字
            keywords = [k for k in keywords if len(k) > 1] or [clean_q]
            
            name_conds = []
            alias_conds = []
            params = []
            for k in keywords:
                name_conds.append("name LIKE %s")
                alias_conds.append("alias LIKE %s")
                params.append(f"%{k}%")
                
            where_name = " AND ".join(name_conds)
            where_alias = " AND ".join(alias_conds)
            final_params = tuple(params + params)
            
            cursor.execute(
                f"SELECT COUNT(*) as total FROM movies WHERE ({where_name}) OR ({where_alias})",
                final_params,
            )
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"SELECT douban_id as mid, name as title, douban_score as rating, year, cover, genres "
                f"FROM movies WHERE ({where_name}) OR ({where_alias}) "
                f"ORDER BY douban_score DESC LIMIT %s OFFSET %s",
                final_params + (size, offset),
            )
            items = cursor.fetchall()
    # 将 genres 字段从 "剧情/犯罪" 转换为列表
    for item in items:
        if item.get("genres"):
            item["genres"] = item["genres"].split("/")
        else:
            item["genres"] = []
    return {"items": items, "total": total, "page": page, "size": size}


# ---------- Neo4j 详情 ----------

def get_movie_detail(session, mid: str) -> Optional[dict]:
    """从 Neo4j 获取电影详情 + 导演 + 演员 + 类型"""
    result = session.run(
        """
        MATCH (m:Movie {mid: $mid})
        OPTIONAL MATCH (m)<-[:DIRECTED]-(d:Person)
        OPTIONAL MATCH (m)<-[act:ACTED_IN]-(a:Person)
        OPTIONAL MATCH (m)-[:HAS_GENRE]->(g:Genre)
        RETURN m, 
               collect(DISTINCT {pid: d.pid, name: d.name}) AS directors,
               collect(DISTINCT {pid: a.pid, name: a.name, order: act.order}) AS actors,
               collect(DISTINCT g.name) AS genres
        """,
        mid=mid,
    )
    record = result.single()
    if not record:
        return None

    m = record["m"]
    directors = [d for d in record["directors"] if d["pid"] is not None]
    actors = [a for a in record["actors"] if a["pid"] is not None]
    # 按 order 排序演员
    actors.sort(key=lambda x: x.get("order") or 999)

    return {
        "mid": m.get("mid"),
        "title": m.get("title") or m.get("name"),
        "rating": m.get("rating"),
        "year": m.get("year"),
        "content_type": m.get("content_type") or m.get("type"),
        "genres": record["genres"],
        "regions": m.get("regions"),
        "cover": m.get("cover"),
        "storyline": m.get("storyline"),
        "url": f"https://movie.douban.com/subject/{m.get('mid')}/",
        "directors": directors,
        "actors": actors,
    }


def get_movie_credits(session, mid: str) -> Optional[dict]:
    """获取电影演职人员"""
    result = session.run(
        """
        MATCH (m:Movie {mid: $mid})
        OPTIONAL MATCH (m)<-[:DIRECTED]-(d:Person)
        OPTIONAL MATCH (m)<-[act:ACTED_IN]-(a:Person)
        RETURN m.mid AS mid,
               collect(DISTINCT {pid: d.pid, name: d.name}) AS directors,
               collect(DISTINCT {pid: a.pid, name: a.name, order: act.order}) AS actors
        """,
        mid=mid,
    )
    record = result.single()
    if not record:
        return None
    directors = [d for d in record["directors"] if d["pid"] is not None]
    actors = [a for a in record["actors"] if a["pid"] is not None]
    actors.sort(key=lambda x: x.get("order") or 999)
    return {"mid": record["mid"], "directors": directors, "actors": actors}


def get_top_movies(session, genre: str = None, limit: int = 20, sort_by: str = "weighted") -> list:
    """高分电影排行（支持加权排序）"""
    # 排序子句
    if sort_by == "votes":
        order_clause = "ORDER BY m.votes DESC"
    elif sort_by == "rating":
        order_clause = "ORDER BY m.rating DESC"
    else:  # weighted (贝叶斯加权)
        order_clause = "ORDER BY (50000 * 7.0 + coalesce(m.votes, 0) * m.rating) / (50000 + coalesce(m.votes, 0)) DESC"

    if genre:
        result = session.run(
            f"""
            MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre {{name: $genre}})
            WHERE m.rating IS NOT NULL
            RETURN m.mid AS mid, m.title AS title, m.rating AS rating,
                   m.votes AS votes, m.year AS year, m.cover AS cover
            {order_clause}
            LIMIT $limit
            """,
            genre=genre, limit=limit,
        )
    else:
        result = session.run(
            f"""
            MATCH (m:Movie)
            WHERE m.rating IS NOT NULL
            RETURN m.mid AS mid, m.title AS title, m.rating AS rating,
                   m.votes AS votes, m.year AS year, m.cover AS cover
            {order_clause}
            LIMIT $limit
            """,
            limit=limit,
        )
    return [dict(record) for record in result]


def get_genres(session) -> list:
    """获取所有类型"""
    result = session.run("MATCH (g:Genre) RETURN g.name AS name ORDER BY g.name")
    return [record["name"] for record in result]


def filter_movies(
    session,
    genre: str = None,
    content_type: str = None,
    year_from: int = None,
    year_to: int = None,
    rating_min: float = None,
    page: int = 1,
    size: int = 20,
    sort_by: str = "weighted",
) -> dict:
    """多条件筛选电影（支持贝叶斯加权排序）"""
    conditions = []
    params: dict = {"skip": (page - 1) * size, "limit": size}

    match_clause = "MATCH (m:Movie)"
    if genre:
        match_clause = "MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre {name: $genre})"
        params["genre"] = genre
    if content_type:
        conditions.append("m.content_type = $content_type")
        params["content_type"] = content_type
    if year_from:
        conditions.append("m.year >= $year_from")
        params["year_from"] = year_from
    if year_to:
        conditions.append("m.year <= $year_to")
        params["year_to"] = year_to
    if rating_min:
        conditions.append("m.rating >= $rating_min")
        params["rating_min"] = rating_min

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # 排序子句
    if sort_by == "votes":
        order_clause = "ORDER BY coalesce(m.votes, 0) DESC"
    elif sort_by == "rating":
        order_clause = "ORDER BY coalesce(m.rating, 0) DESC"
    else:  # weighted（贝叶斯加权，默认）
        order_clause = "ORDER BY (50000 * 7.0 + coalesce(m.votes, 0) * coalesce(m.rating, 0)) / (50000 + coalesce(m.votes, 0)) DESC"

    # 获取总数
    count_q = f"{match_clause} {where_clause} RETURN count(m) AS total"
    total = session.run(count_q, **params).single()["total"]

    # 获取分页数据
    data_q = (
        f"{match_clause} {where_clause} "
        "RETURN m.mid AS mid, m.title AS title, m.rating AS rating, "
        "m.votes AS votes, m.year AS year, m.cover AS cover "
        f"{order_clause} SKIP $skip LIMIT $limit"
    )
    items = [dict(r) for r in session.run(data_q, **params)]

    return {"items": items, "total": total, "page": page, "size": size}
