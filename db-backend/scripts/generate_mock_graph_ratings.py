#!/usr/bin/env python3
"""
生成优质的 Graph-Native 电影模拟评分数据
1. 连接 MySQL 和 Neo4j。
2. 调用 Kimi API 模拟具有特定观影偏好的人群（User Persona），为其拥有的电影进行逻辑打分。
3. 双写：MySQL(`user_movie_ratings`, `users`) & Neo4j(`User` node, `[RATED]` rel)。
"""

import os
import sys
import json
import random
import asyncio
import uuid
import requests
from datetime import datetime, timedelta
from typing import List, Dict

# 将 app 加入 PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.mysql import init_pool, get_connection, close_pool
from app.db.neo4j import Neo4jConnection

KIMI_API_KEY = os.environ.get("KIMI_API_KEY")
KIMI_API_URL = "https://api.moonshot.cn/v1/chat/completions"

PERSONAS = [
    {"name": "硬核科幻迷", "desc": "只喜欢硬科幻和太空题材，对这些电影打分极高（4-5星）。其他类型往往打低分1-3星。"},
    {"name": "资深文艺青年", "desc": "偏爱深刻剧情片、独立电影和欧洲获奖影片，会给这类影片打高分。鄙视商业无脑大片。"},
    {"name": "动作狂热粉", "desc": "热衷于紧张刺激的动作片和悬疑犯罪片的影迷，喜欢大场面。喜欢给经典动作高分。"},
    {"name": "二次元宅", "desc": "尤其喜欢日本动画电影和奇幻动画。给动漫类绝对高分，对真人剧情片评分一般。"},
    {"name": "轻松喜剧控", "desc": "只要是高分喜剧片就会打5星的人，平时工作太累不想看深刻沉重的电影，恐惧惊悚片。"},
]

# 全局存储从数据库拉取的电影候选池
MOVIE_POOL = []

def load_movie_pool():
    print("🚀 正在从数据库拉取电影候选池...")
    init_pool()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 随机拉取 500 部具有类型的知名电影作为 LLM 可选的上下文
            cursor.execute('''
                SELECT douban_id, name, genres 
                FROM movies 
                WHERE genres IS NOT NULL AND genres != ''
                  AND (year < 2026 OR (year = 2026 AND release_date IS NOT NULL AND LEFT(release_date, 10) <= '2026-03-20'))
                ORDER BY RAND() LIMIT 500
            ''')
            rows = cursor.fetchall()
            global MOVIE_POOL
            for r in rows:
                MOVIE_POOL.append({
                    "mid": r['douban_id'],
                    "title": r['name'],
                    "genres": r['genres']
                })
            print(f"✅ 成功加载 {len(MOVIE_POOL)} 部电影供大模型采样。")
    finally:
        conn.close()

async def fetch_llm_ratings(persona: dict, num_users: int = 2) -> List[Dict]:
    """
    请求大模型为特定 Persona 生成若干用户的打分
    """
    if not KIMI_API_KEY:
        # 如果没有 API_KEY，提供一个本地快速伪造的方法（避免阻断执行）
        return generate_dummy_ratings_local(persona, num_users)
        
    prompt_movies = "\n".join([f"- ID:{m['mid']} | 名称:{m['title']} | 类型:{m['genres']}" for m in random.sample(MOVIE_POOL, min(200, len(MOVIE_POOL)))])
    
    prompt = f"""
你是一个专业的用户行为模拟器。现在我需要你模拟 {num_users} 个不同的用户，他们的集体人设是【{persona['name']}】：
{persona['desc']}

以下是我数据库中的部分电影清单（包含ID、名称、类型）：
{prompt_movies}

请基于上述人设，为这 {num_users} 个虚拟用户分别挑选 20-40 部他们看过的电影，并给出符合他们人设逻辑的 `rating`（1.0, 2.0, 3.0, 4.0, 5.0）。
例如：科幻迷会对列表中的科幻片给4-5，对爱情片给1-2。

你必须严格只输出合法的 JSON 格式，不要输出任何 Markdown 标记或多余的文字！格式如下：
{{
  "users": [
    {{
      "username": "User_01",
      "ratings": [
        {{"mid": "1292052", "rating": 5.0}},
        {{"mid": "26683723", "rating": 2.0}}
      ]
    }}
  ]
}}
"""
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "moonshot-v1-8k",
        "messages": [
            {"role": "system", "content": "你是一个只输出 JSON 的数据生成引擎。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.8,
        "response_format": {"type": "json_object"}
    }
    
    print(f"⏳ 请求 Kimi API 生成 [{persona['name']}] 的数据...")
    loop = asyncio.get_event_loop()
    try:
        req = lambda: requests.post(KIMI_API_URL, headers=headers, json=payload, timeout=60)
        res = await loop.run_in_executor(None, req)
        res.raise_for_status()
        content = res.json()['choices'][0]['message']['content']
        data = json.loads(content)
        return data.get("users", [])
    except Exception as e:
        print(f"❌ Kimi API 调用失败或解析 JSON 失败: {e}，将使用本地降级生成。")
        return generate_dummy_ratings_local(persona, num_users)

def generate_dummy_ratings_local(persona: dict, num_users: int) -> List[Dict]:
    """ 降级方案：根据简单的规则在本地直接生成模拟数据以保证流程畅通 """
    if not MOVIE_POOL:
        return []

    users = []
    keyword = "科幻" if "科幻" in persona['name'] else "剧情" if "文艺" in persona['name'] else "动作" if "动作" in persona['name'] else "动画" if "二次元" in persona['name'] else "喜剧"
    
    for i in range(num_users):
        u_id = str(uuid.uuid4())[:8]
        user_data = {"username": f"{persona['name']}_{u_id}", "ratings": []}
        sample_size = min(30, len(MOVIE_POOL))
        selected = random.sample(MOVIE_POOL, sample_size)
        for m in selected:
            if keyword in m['genres']:
                rating = random.choice([4.0, 5.0])
            else:
                rating = random.choice([1.0, 2.0, 3.0])
            user_data["ratings"].append({"mid": m['mid'], "rating": rating})
        users.append(user_data)
    return users


def save_to_mysql_and_neo4j(users_data: List[Dict]):
    """ 双写落库系统 """
    conn = get_connection()
    neo4j_driver = Neo4jConnection.get_driver()
    
    mysql_users_inserted = 0
    mysql_ratings_inserted = 0
    neo4j_nodes_created = 0
    neo4j_edges_created = 0
    
    try:
        with neo4j_driver.session() as session:
            for u in users_data:
                # 1. 写入 MySQL User
                username = u.get('username', f"MockUser_{random.randint(1000,9999)}")
                pwd_hash = "mock_hash"
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO users (username, password_hash, nickname, is_mock) VALUES (%s, %s, %s, %s)",
                            (username, pwd_hash, username, 1)
                        )
                        user_id = cur.lastrowid
                    mysql_users_inserted += 1
                    
                    # 2. 写入 Neo4j User Node
                    session.run(
                        "MERGE (u:User {id: $uid}) "
                        "SET u.username = $uname, u.is_mock = true",
                        uid=user_id,
                        uname=username,
                    )
                    neo4j_nodes_created += 1
                    
                    # 3. 写入 Ratings 两端
                    for r in u.get('ratings', []):
                        mid = str(r['mid'])
                        rating = float(r['rating'])
                        
                        # MySQL
                        with conn.cursor() as cur:
                            cur.execute(
                                "INSERT INTO user_movie_ratings (user_id, mid, rating) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE rating=%s",
                                (user_id, mid, rating, rating)
                            )
                        mysql_ratings_inserted += 1
                        
                        # Neo4j
                        session.run("""
                            MATCH (u:User {id: $uid}), (m:Movie {mid: $mid})
                            MERGE (u)-[rel:RATED]->(m)
                            SET rel.rating = $rating, rel.timestamp = datetime()
                        """, uid=user_id, mid=mid, rating=rating)
                        neo4j_edges_created += 1
                        
                except Exception as e:
                    print(f"⚠️ 保存用户 {username} 的数据时出错: {e}")
    finally:
        conn.close()
                
    print(f"✅ 落库完成: MySQL [{mysql_users_inserted} 用户, {mysql_ratings_inserted} 评分] | Neo4j [{neo4j_nodes_created} 节点, {neo4j_edges_created} 连边]")

async def main():
    print("==============================================")
    print("🎬 基于大模型的图谱打分数据生成引擎 (Graph Mock)")
    print("==============================================")
    
    load_movie_pool()
    if not MOVIE_POOL:
        print("❌ 电影池为空，请先确保 MySQL movies 表中有数据。")
        return

    # 这里我们计划生成共计 5 个 Persona * 20 批 * 2 个 = 200 个用户，约 6000 条数据。
    # 为防止等待过长，脚本每次执行可以只跑少数批次，通过循环增加
    BATCHES = 5
    USERS_PER_BATCH = 2
    
    tasks = []
    for _ in range(BATCHES):
        for p in PERSONAS:
            tasks.append(fetch_llm_ratings(p, USERS_PER_BATCH))
            
    print(f"🚀 发起 {len(tasks)} 个大模型并发请求...")
    results = await asyncio.gather(*tasks)
    
    print("💾 正在执行底层系统的双写持久化...")
    for res in results:
        if res:
            save_to_mysql_and_neo4j(res)
            
    close_pool()
    Neo4jConnection.close()
    print("🎉 所有操作执行完毕！")

if __name__ == "__main__":
    asyncio.run(main())
