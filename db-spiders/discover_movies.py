
import requests
import random
import time
import sys
import os
import string
import pymysql

BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)
from db_spiders.database import connection

def generate_bid():
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(11))

def get_random_ua():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
    ]
    return random.choice(user_agents)

def discover_movies():
    # Proven tags that work with the 'tags=TAG' parameter
    tags = [
        '剧情', '喜剧', '动作', '科幻', '悬疑', '恐怖', '治愈', 
        '爱情', '动画', '犯罪', '奇幻', '冒险', '灾难', '武侠',
        '华语', '欧美', '韩国', '日本', '中国大陆', '美国', '香港', '台湾'
    ]
    
    sort_types = ['U', 'T', 'S'] # U=Hot? T=Time, S=Score
    
    for tag in tags:
        for sort_type in sort_types:
            print(f"\n🔍 Exploring tag: {tag} | Sort: {sort_type}")
            
            # Determine number of movies to fetch per tag (e.g., 2000 per tag)
            # API returns 20 items per request
            limit = 20
            start = 0
            max_start = 500 # Reduced depth per sort, since we have multiple sorts
            
            while start < max_start:
                url = "https://movie.douban.com/j/new_search_subjects"
                params = {
                    'sort': sort_type, 
                    'range': '0,10', # Score range
                    'tags': '',
                    'start': start,
                    # 'genres': ... removed
                    # 'countries': ... removed
                }
            
            # Special handling for "features" tags is tricky in this API, usually 'tags' or 'genres' works.
            # Simplified approach: put tag in 'q' or just iterate known valid tags structure.
            # Actually, 'tags' parameter supports multiple comma separated values.
            # Let's try to map our tags to the correct param.
            
            # Simplified parameter logic based on debugging
            # Just use the tag directly in the 'tags' parameter.
            params['tags'] = tag
            # Remove other specific params to avoid conflicts
            if 'genres' in params: del params['genres']
            if 'countries' in params: del params['countries']
            
            headers = {
                'User-Agent': get_random_ua(),
                'Cookie': f'bid={generate_bid()}'
            }
            
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get('data', [])
                    
                    if not items:
                        print(f"  - No more items for {tag}")
                        break
                        
                    # Insert into DB
                    cursor = connection.cursor()
                    added_batch = 0
                    for item in items:
                        douban_id = item.get('id')
                        title = item.get('title')
                        if not douban_id: continue
                        
                        try:
                            # Use INSERT IGNORE
                            sql = "INSERT IGNORE INTO subjects (douban_id, type) VALUES (%s, 'movie')"
                            cursor.execute(sql, (douban_id,))
                            if cursor.rowcount > 0:
                                added_batch += 1
                        except Exception as e:
                            print(f"Order error: {e}")
                    
                    connection.commit()
                    total_added += added_batch
                    print(f"  - Offset {start}: Found {len(items)}, New {added_batch}")
                    
                    start += limit
                    time.sleep(random.uniform(1.0, 2.0)) # Be polite
                    
                else:
                    print(f"  - Error {resp.status_code}")
                    time.sleep(5)
                    
            except Exception as e:
                print(f"  - Request failed: {e}")
                time.sleep(5)
                
    print(f"\n✅ Discovery complete. Total new movies added: {total_added}")

if __name__ == '__main__':
    discover_movies()
