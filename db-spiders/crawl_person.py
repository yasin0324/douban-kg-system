#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
High-Performance Douban Person Crawler with Proxy Pool (Async Version)
Based on proxy_crawler.py architecture for movie crawling.

Features:
- Async Playwright with Global Singleton Browser
- Dynamic IP Replacement (Maintains constant IP pool)
- Full Person Data Extraction (name, sex, birth, profession, biography, etc.)
- BID Cookie Injection
- Auto-Retirement of burned IPs
"""

import os
import sys
import time
import random
import asyncio
import re
import string
import threading
from playwright.async_api import async_playwright

# Add current directory to path
BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)

from db_spiders.database import connection
from db_spiders import validator
from proxy_manager import ProxyManager

# ================= CONFIGURATION =================
# DEVICE CONFIGURATION
IPS_PER_BATCH = 30     
WORKERS_PER_IP = 10    
MAX_IP_LIFE_SECONDS = 4500  # 1 hour max (backup safeguard, errors auto-retire IP earlier)
MAX_CONSECUTIVE_ERRORS = 6  # If IP fails 6 times in a row, retire it

# REQUEST CONFIGURATION
REQUEST_DELAY_MIN = 2.5  # Min delay between requests
REQUEST_DELAY_MAX = 4.5  # Max delay between requests
STARTUP_JITTER_MIN = 0.5
STARTUP_JITTER_MAX = 4.0

# ANTI-DETECTION
INITIAL_IPS = 2  # Start with fewer IPs to warm up gradually
RAMP_UP_INTERVAL = 60  # Seconds between adding new IPs

# WORKER RAMP-UP PER IP
INITIAL_WORKERS_PER_IP = 1  # Start with fewer workers per IP
WORKER_RAMP_UP_INTERVAL = 15  # Seconds between adding workers per IP
WORKER_RAMP_UP_COUNT = 1  # How many workers to add each time

# GLOBAL RESOURCES
PROXY_MANAGER = ProxyManager()
STOP_EVENT = asyncio.Event()

# Statistics
stats = {
    'inserted': 0,
    'updated': 0,
    'skipped': 0,
    'failed': 0,
    'not_found': 0
}
stats_lock = threading.Lock()

# Person table fields
PERSON_FIELDS = [
    'person_id', 'name', 'sex', 'name_en', 'name_zh',
    'birth', 'death', 'birthplace', 'profession', 'biography'
]

# Thread-safe lock for database operations
db_lock = threading.Lock()


def generate_bid():
    """Generate random BID for Douban"""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(11))


def get_random_ua():
    """Get a random modern User-Agent"""
    user_agents = [
        # Chrome Windows (多版本)
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        # Chrome Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Safari Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        # Edge Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        # Edge Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        # Firefox Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        # Firefox Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.0; rv:121.0) Gecko/20100101 Firefox/121.0",
        # Opera Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 OPR/105.0.0.0",
        # Windows 11
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    return random.choice(user_agents)


def get_browser_headers(user_agent):
    """Generate realistic browser headers to avoid detection"""
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Cache-Control': 'max-age=0',
        'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"' if 'Windows' in user_agent else '"macOS"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': user_agent,
    }
    return headers


# ================= DATABASE OPERATIONS =================

def reset_stale_person_tasks(cursor=None):
    """Reset tasks that have been locked for too long (e.g. crashed workers)"""
    sql = '''
        UPDATE person_obj 
        SET status = 0 
        WHERE status = 1 
        AND TIMESTAMPDIFF(MINUTE, created_at, NOW()) > 30
    '''
    
    if cursor is None:
        with db_lock:
            try:
                cursor = connection.cursor()
                cursor.execute(sql)
                connection.commit()
            except Exception:
                pass
            finally:
                try:
                    cursor.close()
                except:
                    pass
    else:
        try:
            cursor.execute(sql)
            connection.commit()
        except Exception:
            pass


def fetch_open_person_tasks(limit=1000):
    """
    Fetch open tasks (status=0) WITHOUT locking them.
    Used for JIT locking.
    """
    with db_lock:
        cursor = connection.cursor()
        sql = '''
            SELECT po.person_id 
            FROM person_obj po
            LEFT JOIN person p ON po.person_id = p.person_id
            WHERE p.person_id IS NULL
            AND po.status = 0
            ORDER BY po.person_id DESC
            LIMIT %s
        '''
        cursor.execute(sql, (limit,))
        return [row['person_id'] for row in cursor.fetchall()]


def try_claim_person_task(person_id):
    """
    Atomically try to lock a person task.
    Returns True if successfully locked, False otherwise.
    """
    with db_lock:
        cursor = connection.cursor()
        try:
            cursor.execute('''
                UPDATE person_obj 
                SET status = 1 
                WHERE person_id = %s AND status = 0
            ''', (person_id,))
            connection.commit()
            return cursor.rowcount > 0
        except:
            return False


def release_person_task(person_id):
    """Reset task status to 0 (e.g. for retry)"""
    with db_lock:
        cursor = connection.cursor()
        try:
            cursor.execute('UPDATE person_obj SET status = 0 WHERE person_id = %s', (person_id,))
            connection.commit()
        except:
            pass


def mark_person_crawl_failed(person_id):
    """Mark a person as failed to crawl (404, etc.)"""
    with db_lock:
        cursor = connection.cursor()
        try:
            cursor.execute('UPDATE person_obj SET status = 3 WHERE person_id = %s', (person_id,))
            connection.commit()
        except:
            pass


def save_person_to_database(data):
    """Save person data to database (thread-safe)"""
    with db_lock:
        cursor = connection.cursor()
        person_id = data['person_id']
        
        # Check if already exists
        cursor.execute("SELECT person_id FROM person WHERE person_id = %s", (person_id,))
        exists = cursor.fetchone()
        
        if exists:
            # Update existing record
            update_fields = [f for f in PERSON_FIELDS if f != 'person_id']
            set_clause = ', '.join([f"{f} = %s" for f in update_fields])
            values = [data.get(f) for f in update_fields] + [person_id]
            sql = f"UPDATE person SET {set_clause} WHERE person_id = %s"
            try:
                cursor.execute(sql, values)
                connection.commit()
                # Mark as completed in person_obj
                cursor.execute('UPDATE person_obj SET status = 2 WHERE person_id = %s', (person_id,))
                connection.commit()
                return "updated"
            except Exception as e:
                connection.rollback()
                return "failed"
        
        # Insert new person
        values = [data.get(f) for f in PERSON_FIELDS]
        placeholders = ', '.join(['%s'] * len(PERSON_FIELDS))
        field_names = ', '.join(PERSON_FIELDS)
        
        sql = f"INSERT INTO person ({field_names}) VALUES ({placeholders})"
        
        try:
            cursor.execute(sql, values)
            connection.commit()
            # Mark as completed in person_obj
            cursor.execute('UPDATE person_obj SET status = 2 WHERE person_id = %s', (person_id,))
            connection.commit()
            return "inserted"
        except Exception as e:
            connection.rollback()
            return "failed"


# ================= ASYNC EXTRACTION =================

async def async_extract_person_data(page, person_id):
    """
    Extract person data from Douban celebrity page.
    URL format: https://movie.douban.com/celebrity/{person_id}/
    """
    try:
        # Wait for content to load
        try:
            await page.wait_for_selector('#content', timeout=10000)
        except:
            return None
        
        data = {'person_id': person_id}
        
        # Helper for safely getting text
        async def get_text(selector):
            try:
                loc = page.locator(selector).first
                if await loc.count() > 0:
                    return await loc.inner_text()
            except:
                pass
            return None
        
        # Name (from h1)
        try:
            name = await get_text('#content h1')
            if name:
                data['name'] = name.strip()
            else:
                data['name'] = None
        except:
            data['name'] = None
        
        # Get all info items from the info block
        info_text = await get_text('#headline .info')
        
        if info_text:
            lines = info_text.split('\n')
            for line in lines:
                line = line.strip()
                
                # Sex
                if '性别:' in line or '性别：' in line:
                    sex = line.replace('性别:', '').replace('性别：', '').strip()
                    if '男' in sex:
                        data['sex'] = '男'
                    elif '女' in sex:
                        data['sex'] = '女'
                    else:
                        data['sex'] = None
                
                # English name
                elif '外文名:' in line or '外文名：' in line or '英文名:' in line or '英文名：' in line:
                    name_en = line.replace('外文名:', '').replace('外文名：', '')
                    name_en = name_en.replace('英文名:', '').replace('英文名：', '').strip()
                    data['name_en'] = name_en if name_en else None
                
                # More Chinese names
                elif '更多中文名:' in line or '更多中文名：' in line:
                    name_zh = line.replace('更多中文名:', '').replace('更多中文名：', '').strip()
                    data['name_zh'] = name_zh if name_zh else None
                
                # Birth date
                elif '出生日期:' in line or '出生日期：' in line:
                    birth_str = line.replace('出生日期:', '').replace('出生日期：', '').strip()
                    data['birth'] = validator.str_to_date(validator.match_date(birth_str))
                
                # Death date
                elif '死亡日期:' in line or '死亡日期：' in line:
                    death_str = line.replace('死亡日期:', '').replace('死亡日期：', '').strip()
                    data['death'] = validator.str_to_date(validator.match_date(death_str))
                
                # Birthplace
                elif '出生地:' in line or '出生地：' in line:
                    birthplace = line.replace('出生地:', '').replace('出生地：', '').strip()
                    data['birthplace'] = birthplace if birthplace else None
                
                # Profession
                elif '职业:' in line or '职业：' in line:
                    profession = line.replace('职业:', '').replace('职业：', '').strip()
                    data['profession'] = profession if profession else None
        
        # Set defaults for missing fields
        for field in ['sex', 'name_en', 'name_zh', 'birth', 'death', 'birthplace', 'profession']:
            if field not in data:
                data[field] = None
        
        # Biography - try to get full version first, then short version
        try:
            # Try to get the full biography (hidden by default)
            bio = await get_text('div#intro .bd .all')
            if not bio:
                # Try short version
                bio = await get_text('div#intro .bd span.short')
                if not bio:
                    # Try direct content
                    bio = await get_text('div#intro .bd')
            
            if bio:
                # Clean up biography text
                bio = bio.replace('(展开全部)', '').replace('展开全部', '').strip()
                data['biography'] = bio if bio else None
            else:
                data['biography'] = None
        except:
            data['biography'] = None
        
        return data
        
    except Exception as e:
        return None


# ================= CORE LOGIC =================

async def run_ip_group(ip_id, proxy_config, q, global_sem, group_finished_callback):
    """
    Runs a group of workers for a single IP.
    Terminates if IP expires or hits error limit.
    Workers are ramped up gradually to avoid 429.
    """
    print(f"[{ip_id}] 🔥 Powering up with IP: {proxy_config['server'].split('@')[-1]}")
    
    tasks = []
    consecutive_errors = 0
    start_time = time.time()
    
    # Shared state for this group
    group_state = {
        'active': True,
        'current_workers': 0,
        'max_workers': INITIAL_WORKERS_PER_IP,
        'worker_id_counter': 0
    }
    
    async def single_worker(w_id):
        nonlocal consecutive_errors
        
        await asyncio.sleep(random.uniform(STARTUP_JITTER_MIN, STARTUP_JITTER_MAX))
        
        while group_state['active'] and not STOP_EVENT.is_set():
            async with global_sem:
                try:
                    # Check life
                    if time.time() - start_time > MAX_IP_LIFE_SECONDS:
                        print(f"[{ip_id}] ⏰ Expired.")
                        break
                    
                    try:
                        person_id = q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    
                    # JIT LOCKING - Try to lock the task atomically
                    loop = asyncio.get_event_loop()
                    locked = await loop.run_in_executor(None, try_claim_person_task, person_id)
                    if not locked:
                        q.task_done()
                        continue
                    
                    context = None
                    try:
                        # Create new context with proxy
                        ua = get_random_ua()
                        context = await GLOBAL_BROWSER.new_context(
                            proxy=proxy_config,
                            user_agent=ua,
                            viewport={'width': 1920, 'height': 1080},
                            locale='zh-CN',
                            java_script_enabled=True,
                            extra_http_headers=get_browser_headers(ua),
                            ignore_https_errors=True,
                        )
                        
                        bid = generate_bid()
                        await context.add_cookies([{
                            'name': 'bid', 'value': bid, 'domain': '.douban.com', 'path': '/'
                        }])
                        
                        page = await context.new_page()
                        
                        # Block images and media for faster loading
                        await page.route("**/*", lambda route: route.abort() 
                            if route.request.resource_type in ["image", "media", "font"] 
                            else route.continue_()
                        )
                        
                        # Small delay for proxy stabilization
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        
                        url = f'https://www.douban.com/personage/{person_id}/'
                        
                        try:
                            response = await page.goto(url, wait_until='domcontentloaded', timeout=20000)
                        except Exception as e:
                            consecutive_errors += 1
                            await loop.run_in_executor(None, release_person_task, person_id)
                            q.put_nowait(person_id)
                            raise e
                        
                        status = response.status
                        if status in [403, 429]:
                            print(f"[{w_id}] ⚠️ {status} Blocked!")
                            consecutive_errors += 1
                            await loop.run_in_executor(None, release_person_task, person_id)
                            q.put_nowait(person_id)
                            
                            if consecutive_errors > MAX_CONSECUTIVE_ERRORS:
                                print(f"[{ip_id}] 💥 Melted! Too many errors. Retiring IP.")
                                group_state['active'] = False
                            continue
                        
                        consecutive_errors = 0
                        
                        if status == 404:
                            with stats_lock:
                                stats['not_found'] += 1
                            await loop.run_in_executor(None, mark_person_crawl_failed, person_id)
                            continue
                        
                        data = await async_extract_person_data(page, person_id)
                        
                        if data and data.get('name'):
                            res = await loop.run_in_executor(None, save_person_to_database, data)
                            
                            if res == "inserted":
                                print(f"[{w_id}] ✅ Saved {person_id}: {data['name']}")
                                with stats_lock:
                                    stats['inserted'] += 1
                            elif res == "updated":
                                print(f"[{w_id}] ↻ Updated {person_id}")
                                with stats_lock:
                                    stats['updated'] += 1
                            else:
                                with stats_lock:
                                    stats['failed'] += 1
                        else:
                            with stats_lock:
                                stats['failed'] += 1
                            await loop.run_in_executor(None, release_person_task, person_id)
                        
                    except Exception as e:
                        await loop.run_in_executor(None, release_person_task, person_id)
                        pass
                    finally:
                        if context:
                            try:
                                await context.close()
                            except:
                                pass
                        q.task_done()
                        
                except Exception as e:
                    pass
            
            await asyncio.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))
    
    # Worker ramp-up manager
    async def worker_ramp_up_manager():
        """Gradually spawn more workers over time"""
        last_ramp = time.time()
        
        while group_state['active'] and not STOP_EVENT.is_set():
            now = time.time()
            
            if (now - last_ramp > WORKER_RAMP_UP_INTERVAL and 
                group_state['max_workers'] < WORKERS_PER_IP):
                
                old_max = group_state['max_workers']
                group_state['max_workers'] = min(
                    group_state['max_workers'] + WORKER_RAMP_UP_COUNT, 
                    WORKERS_PER_IP
                )
                
                new_workers_needed = group_state['max_workers'] - group_state['current_workers']
                for _ in range(new_workers_needed):
                    wid = group_state['worker_id_counter']
                    group_state['worker_id_counter'] += 1
                    group_state['current_workers'] += 1
                    tasks.append(asyncio.create_task(single_worker(f"{ip_id}-W{wid}")))
                
                if old_max != group_state['max_workers']:
                    print(f"[{ip_id}] 📈 Workers: {group_state['current_workers']}/{WORKERS_PER_IP}")
                last_ramp = now
            
            await asyncio.sleep(2)
    
    # Spawn initial workers
    for i in range(INITIAL_WORKERS_PER_IP):
        group_state['worker_id_counter'] += 1
        group_state['current_workers'] += 1
        tasks.append(asyncio.create_task(single_worker(f"{ip_id}-W{i}")))
    
    # Start ramp-up manager
    ramp_task = asyncio.create_task(worker_ramp_up_manager())
    
    # Wait for all workers to finish
    await asyncio.gather(*tasks, return_exceptions=True)
    
    # Cancel ramp-up manager
    ramp_task.cancel()
    try:
        await ramp_task
    except asyncio.CancelledError:
        pass
    
    group_finished_callback(ip_id)


async def main():
    global GLOBAL_BROWSER
    
    print(f"🚀 Starting Douban Person Crawler with Proxy Pool")
    print(f"⚙️ Target Pool: {IPS_PER_BATCH} active IPs (starting with {INITIAL_IPS}, ramping up)")
    print(f"📊 Pending persons in person_obj: checking...")
    
    # Check pending count
    with db_lock:
        cursor = connection.cursor()
        cursor.execute('''
            SELECT COUNT(*) as cnt FROM person_obj po
            LEFT JOIN person p ON po.person_id = p.person_id
            WHERE p.person_id IS NULL AND po.status = 0
        ''')
        pending = cursor.fetchone()['cnt']
        print(f"📊 Pending persons: {pending}")
    
    # Reset stale locks
    print("🧹 Resetting stale locks...")
    reset_stale_person_tasks()
    
    async with async_playwright() as p:
        GLOBAL_BROWSER = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
        )
        
        global_sem = asyncio.Semaphore(INITIAL_IPS * WORKERS_PER_IP)
        q = asyncio.Queue()
        
        async def fill_queue():
            while True:
                if q.qsize() < 200:
                    loop = asyncio.get_event_loop()
                    new_ids = await loop.run_in_executor(None, fetch_open_person_tasks, 500)
                    if not new_ids and q.qsize() == 0:
                        print("🏁 Database exhausted.")
                        STOP_EVENT.set()
                        break
                    for pid in new_ids:
                        await q.put(pid)
                    print(f"📚 Refilled Queue: {q.qsize()}")
                await asyncio.sleep(10)
        
        asyncio.create_task(fill_queue())
        
        # Group Management
        active_groups = set()
        group_tasks = []
        
        def on_group_finish(gid):
            if gid in active_groups:
                active_groups.remove(gid)
        
        ip_counter = 0
        last_ramp_up = time.time()
        current_max_ips = INITIAL_IPS
        
        while not STOP_EVENT.is_set():
            # Gradual IP ramp-up
            now = time.time()
            if now - last_ramp_up > RAMP_UP_INTERVAL and current_max_ips < IPS_PER_BATCH:
                current_max_ips = min(current_max_ips + 2, IPS_PER_BATCH)
                print(f"📈 Ramping up: max IPs now = {current_max_ips}")
                last_ramp_up = now
            
            # Maintain pool size
            needed = current_max_ips - len(active_groups)
            
            if needed > 0:
                print(f"🔧 Pool Low ({len(active_groups)}/{current_max_ips}). Fetching {needed} IPs...")
                loop = asyncio.get_event_loop()
                proxies = await loop.run_in_executor(None, PROXY_MANAGER.fetch_proxies, needed)
                
                if proxies:
                    for proxy in proxies:
                        ip_counter += 1
                        gid = f"IP{ip_counter}"
                        active_groups.add(gid)
                        t = asyncio.create_task(
                            run_ip_group(gid, proxy, q, global_sem, on_group_finish)
                        )
                        group_tasks.append(t)
                else:
                    print("⚠️ Fetch failed. Retrying in 10s...")
                    await asyncio.sleep(10)
            
            # Print status
            sys.stdout.write(f"\r⚡ Active IPs: {len(active_groups)} | Queue: {q.qsize()} | Ins: {stats['inserted']} | Fail: {stats['failed']}")
            sys.stdout.flush()
            
            await asyncio.sleep(2)
            
            # Clean up finished tasks
            group_tasks = [t for t in group_tasks if not t.done()]
            
            if STOP_EVENT.is_set() and len(active_groups) == 0:
                break
        
        await GLOBAL_BROWSER.close()
    
    print(f"\n\n{'='*50}")
    print(f"📊 Final Statistics:")
    print(f"   ✅ Inserted: {stats['inserted']}")
    print(f"   ↻ Updated: {stats['updated']}")
    print(f"   ❌ Failed: {stats['failed']}")
    print(f"   🔍 Not Found: {stats['not_found']}")
    print(f"{'='*50}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Douban Person Crawler with Proxy Pool')
    parser.add_argument('--ips', type=int, default=IPS_PER_BATCH, help='Number of IPs in pool')
    parser.add_argument('--workers', type=int, default=WORKERS_PER_IP, help='Workers per IP')
    parser.add_argument('--initial-ips', type=int, default=INITIAL_IPS, help='Initial IPs to start with')
    parser.add_argument('--initial-workers', type=int, default=INITIAL_WORKERS_PER_IP, help='Initial workers per IP')
    args = parser.parse_args()
    
    IPS_PER_BATCH = args.ips
    WORKERS_PER_IP = args.workers
    INITIAL_IPS = args.initial_ips
    INITIAL_WORKERS_PER_IP = args.initial_workers
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopped.")
