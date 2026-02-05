#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
High-Performance Douban Crawler with Proxy Pool (Async Version)
Uses Asyncio + Playwright for massive concurrency with a single browser process.
Features:
- Global Singleton Browser
- Dynamic IP Replacement (Maintains constant IP pool)
- Full Data Extraction (Matches sync version)
- BID Cookie Injection
- Auto-Retirement of burn IPs
"""

import os
import sys
import time
import random
import asyncio
import re
import string
from playwright.async_api import async_playwright

# Add current directory to path
BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)

from db_spiders.database import connection
from db_spiders import validator
from proxy_manager import ProxyManager
from crawl_movie import (
    get_uncrawled_movies, 
    mark_crawl_failed,
    save_new_seeds, 
    save_to_database, 
    save_to_database, 
    get_random_ua,
    fetch_open_tasks,
    try_claim_task, 
    release_task,
    reset_stale_tasks,
    stats, stats_lock
)

# ================= CONFIGURATION =================
# DEVICE CONFIGURATION
IPS_PER_BATCH = 30     
WORKERS_PER_IP = 10    
MAX_IP_LIFE_SECONDS = 1800 # 30 mins max life just in case
MAX_CONSECUTIVE_ERRORS = 5 # If IP fails 5 times in a row, retire it

# REQUEST CONFIGURATION - Tuned for Windows
REQUEST_DELAY_MIN = 2.5  # Min delay between requests (increased for Windows)
REQUEST_DELAY_MAX = 4.5  # Max delay between requests
STARTUP_JITTER_MIN = 0.5
STARTUP_JITTER_MAX = 4.0

# ANTI-DETECTION - Reduce aggressiveness on Windows
INITIAL_IPS = 2  # Start with fewer IPs to warm up gradually
RAMP_UP_INTERVAL = 60  # Seconds between adding new IPs

# WORKER RAMP-UP PER IP
INITIAL_WORKERS_PER_IP = 2  # Start with fewer workers per IP
WORKER_RAMP_UP_INTERVAL = 25  # Seconds between adding workers per IP
WORKER_RAMP_UP_COUNT = 2  # How many workers to add each time

# GLOBAL RESOURCES
PROXY_MANAGER = ProxyManager()
STOP_EVENT = asyncio.Event()

def generate_bid():
    """Generate random BID for Douban"""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(11))

def get_browser_headers(user_agent):
    """Generate realistic browser headers to avoid detection"""
    # Determine if it's Chrome, Firefox, Safari, or Edge based on UA
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
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

# ================= ASYNC EXTRACTION HELPERS =================

async def async_extract_movie_data(page, douban_id):
    """Async version of data extraction"""
    try:
        # Wait for content
        try:
            await page.wait_for_selector('#content', timeout=10000)
        except:
            return None
            
        data = {'douban_id': douban_id}
        
        # Helper for safely getting text
        async def get_text(selector):
            try:
                loc = page.locator(selector).first
                if await loc.count() > 0:
                    return await loc.inner_text()
            except:
                pass
            return None

        # Name
        data['name'] = await get_text('h1 span[property="v:itemreviewed"]')
        if not data['name']:
            title = await page.title()
            data['name'] = title.replace(' (豆瓣)', '').strip()
            
        # Year
        year_text = await get_text('span.year')
        data['year'] = validator.match_year(year_text) if year_text else None
        
        # Type
        episodes = await page.locator('span:text("集数:")').count()
        data['type'] = 'tv' if episodes > 0 else 'movie'
        
        # Cover
        try:
            img = page.locator('img[rel="v:image"]').first
            src = await img.get_attribute('src')
            if src and 'default' not in src:
                data['cover'] = src.replace('spst', 'lpst').replace('mpic', 'lpic')
            else:
                data['cover'] = None
        except:
            data['cover'] = None

        # Info Block
        info_text = await get_text('#info')
        if info_text:
            for line in info_text.split('\n'):
                if '制片国家/地区:' in line: data['regions'] = line.split('制片国家/地区:')[1].strip()
                if '语言:' in line: data['languages'] = line.split('语言:')[1].strip()
                if '又名:' in line: data['alias'] = validator.process_slash_str(line.split('又名:')[1].strip())
                if '官方网站:' in line: data['official_site'] = line.split('官方网站:')[1].strip()
        else:
            data['regions'] = data['languages'] = data['alias'] = data['official_site'] = None

        # Directors & IDs
        try:
            director_links = await page.locator('a[rel="v:directedBy"]').all()
            director_ids = []
            director_names = []
            for link in director_links:
                href = await link.get_attribute('href')
                name = await link.inner_text()
                if href:
                    did = href.split('/')[-2]
                    director_ids.append(f"{name}:{did}")
                    director_names.append(name)
            data['director_ids'] = '|'.join(director_ids) if director_ids else None
            data['directors'] = '/'.join(director_names) if director_names else None
        except:
            data['director_ids'] = None
            data['directors'] = None
            
        # Actors & IDs
        try:
            actor_links = await page.locator('a[rel="v:starring"]').all()
            actor_ids = []
            actor_names = []
            for link in actor_links:
                href = await link.get_attribute('href')
                name = await link.inner_text()
                if href:
                    aid = href.split('/')[-2]
                    actor_ids.append(f"{name}:{aid}")
                    actor_names.append(name)
            data['actor_ids'] = '|'.join(actor_ids) if actor_ids else None
            data['actors'] = '/'.join(actor_names) if actor_names else None
        except:
             data['actor_ids'] = None
             data['actors'] = None

        # Genres
        genres = await page.locator('span[property="v:genre"]').all_text_contents()
        data['genres'] = '/'.join(genres) if genres else None
        
        # Date
        try:
            date_el = page.locator('span[property="v:initialReleaseDate"]').first
            if await date_el.count() > 0:
                date_str = await date_el.get_attribute('content')
                data['release_date'] = validator.str_to_date(validator.match_date(date_str))
            else:
                data['release_date'] = None
        except:
            data['release_date'] = None
            
        # Mins
        try:
            runtime_el = page.locator('span[property="v:runtime"]').first
            if await runtime_el.count() > 0:
                runtime = await runtime_el.get_attribute('content')
                data['mins'] = int(runtime) if runtime else None
            else:
                data['mins'] = None
        except:
            data['mins'] = None

        # Score
        score = await get_text('strong[property="v:average"]')
        data['douban_score'] = float(score) if score else None
        
        votes = await get_text('span[property="v:votes"]')
        data['douban_votes'] = int(votes) if votes else None
        
        # IMDb
        try:
            imdb_link = page.locator('a:has-text("IMDb")').first
            if await imdb_link.count() > 0:
                href = await imdb_link.get_attribute('href')
                data['imdb_id'] = href.strip().split('?')[0][26:] if href else None
            else:
                data['imdb_id'] = None
        except:
            data['imdb_id'] = None
            
        # Storyline
        story = await get_text('span.all.hidden')
        if not story:
            summary = await page.locator('span[property="v:summary"]').all_text_contents()
            story = '\n'.join([p.strip() for p in summary])
        data['storyline'] = story.strip() if story else None
        

        
        return data
    except Exception as e:
        return None

async def async_extract_related(page):
    try:
        links = await page.locator('#recommendations dl dd a').all()
        ids = []
        for link in links:
            href = await link.get_attribute('href')
            if href and 'subject' in href:
                import re
                match = re.search(r'subject/(\d+)', href)
                if match:
                    ids.append(match.group(1))
        return list(set(ids))
    except:
        return []

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
        'max_workers': INITIAL_WORKERS_PER_IP,  # Start with fewer workers
        'worker_id_counter': 0
    }
    
    async def single_worker(w_id):
        nonlocal consecutive_errors
        
        await asyncio.sleep(random.uniform(STARTUP_JITTER_MIN, STARTUP_JITTER_MAX)) # startup jitter
        
        while group_state['active'] and not STOP_EVENT.is_set():
            async with global_sem:
                try:
                    # Check life
                    if time.time() - start_time > MAX_IP_LIFE_SECONDS:
                        print(f"[{ip_id}] ⏰ Expired.")
                        break
                        
                    try:
                        movie_id = q.get_nowait()
                    except asyncio.QueueEmpty:
                        break # Queue empty

                    # === JIT LOCKING START ===
                    # Try to lock the task atomically
                    loop = asyncio.get_event_loop()
                    locked = await loop.run_in_executor(None, try_claim_task, movie_id)
                    if not locked:
                         # Task already taken by another worker/instance or completed
                        #  print(f"[{w_id}] 🔒 Failed to lock {movie_id}, skipping...")
                         q.task_done()
                         continue
                    # === JIT LOCKING END ===
                    
                    context = None
                    try:
                        # NEW: Inject BID with realistic headers
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
                        
                        # Add request interception for blocking resources
                        await page.route("**/*", lambda route: route.abort() 
                            if route.request.resource_type in ["image", "media", "font"] 
                            else route.continue_()
                        )
                        
                        # Small delay to allow proxy to stabilize
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        
                        url = f'https://movie.douban.com/subject/{movie_id}/'
                        
                        try:
                            response = await page.goto(url, wait_until='domcontentloaded', timeout=20000)
                        except Exception as e:
                            # print(f"[{w_id}] ❌ Net: {e}")
                            consecutive_errors += 1
                            # Unlock for retry
                            await loop.run_in_executor(None, release_task, movie_id) 
                            q.put_nowait(movie_id) # Retry
                            raise e
                            
                        status = response.status
                        if status in [403, 429]:
                            print(f"[{w_id}] ⚠️ {status} Blocked!")
                            consecutive_errors += 1
                            # Unlock for retry
                            await loop.run_in_executor(None, release_task, movie_id)
                            q.put_nowait(movie_id)
                            
                            # Check fuse
                            if consecutive_errors > MAX_CONSECUTIVE_ERRORS:
                                print(f"[{ip_id}] 💥 Melted! Too many errors. Retiring IP.")
                                group_state['active'] = False
                            continue
                            
                        # Success reset
                        consecutive_errors = 0
                        
                        if status == 404:
                             with stats_lock: stats['not_found'] += 1
                             await loop.run_in_executor(None, mark_crawl_failed, movie_id)
                             continue

                        data = await async_extract_movie_data(page, movie_id)
                        
                        if data:
                            loop = asyncio.get_event_loop()
                            res = await loop.run_in_executor(None, save_to_database, data)
                            
                            if res == "inserted":
                                print(f"[{w_id}] ✅ Saved {movie_id}: {data['name']}")
                                with stats_lock: stats['inserted'] += 1
                            elif res == "updated":
                                 print(f"[{w_id}] ↻ Updated {movie_id}")
                                 with stats_lock: stats['updated'] += 1
                            else:
                                 with stats_lock: stats['skipped'] += 1

                            related = await async_extract_related(page)
                            if related:
                                await loop.run_in_executor(None, save_new_seeds, related)
                        else:
                             # print(f"[{w_id}] ❌ Extract Failed {movie_id}")
                             with stats_lock: stats['failed'] += 1
                             # Release task so it can be retried or inspected later
                             await loop.run_in_executor(None, release_task, movie_id)
                            
                    except Exception as e:
                        # print(f"[{w_id}] Err: {e}")
                        # Ensure we release the lock on unexpected errors
                        await loop.run_in_executor(None, release_task, movie_id)
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
            
            # Time to add more workers?
            if (now - last_ramp > WORKER_RAMP_UP_INTERVAL and 
                group_state['max_workers'] < WORKERS_PER_IP):
                
                old_max = group_state['max_workers']
                group_state['max_workers'] = min(
                    group_state['max_workers'] + WORKER_RAMP_UP_COUNT, 
                    WORKERS_PER_IP
                )
                
                # Spawn new workers up to the new max
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
    
    # Callback to notify main loop this group is dead
    group_finished_callback(ip_id)

async def main():
    global GLOBAL_BROWSER
    
    print(f"🚀 Starting Dynamic Async Proxy Crawler")
    print(f"⚙️ Target Pool: {IPS_PER_BATCH} active IPs (starting with {INITIAL_IPS}, ramping up)")
    
    # Prerequisite: Reset any stale locks from previous crashes
    print("🧹 Resetting stale locks...")
    reset_stale_tasks()
    
    async with async_playwright() as p:
        GLOBAL_BROWSER = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
        )
        
        # Use INITIAL_IPS for semaphore, will expand
        global_sem = asyncio.Semaphore(INITIAL_IPS * WORKERS_PER_IP)
        
        # Queue Management
        q = asyncio.Queue()
        
        async def fill_queue():
            # Keep queue filled
            while True:
                if q.qsize() < 200:
                    loop = asyncio.get_event_loop()
                    # Use fetch_open_tasks instead of get_uncrawled_movies (no locking)
                    new_ids = await loop.run_in_executor(None, fetch_open_tasks, 500)
                    if not new_ids and q.qsize() == 0:
                        print("🏁 Database exhausted.")
                        STOP_EVENT.set()
                        break
                    for mid in new_ids:
                        await q.put(mid)
                    print(f"📚 Refilled Queue: {q.qsize()}")
                await asyncio.sleep(10)
        
        asyncio.create_task(fill_queue())
        
        # Group Management
        active_groups = set() # Store IP IDs
        group_tasks = []
        
        def on_group_finish(gid):
            if gid in active_groups:
                active_groups.remove(gid)
                
        ip_counter = 0
        last_ramp_up = time.time()
        current_max_ips = INITIAL_IPS
        
        while not STOP_EVENT.is_set():
            # Gradually ramp up IP count to avoid detection
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
            sys.stdout.write(f"\r⚡ Active IPs: {len(active_groups)} | Queue: {q.qsize()} | Ins: {stats['inserted']}")
            sys.stdout.flush()
            
            await asyncio.sleep(2)
            
            # Clean up finished tasks
            group_tasks = [t for t in group_tasks if not t.done()]
            
            if STOP_EVENT.is_set() and len(active_groups) == 0:
                break
                
        await GLOBAL_BROWSER.close()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--ips', type=int, default=IPS_PER_BATCH)
    parser.add_argument('--workers', type=int, default=WORKERS_PER_IP)
    parser.add_argument('--initial-ips', type=int, default=INITIAL_IPS)
    parser.add_argument('--initial-workers', type=int, default=INITIAL_WORKERS_PER_IP)
    args = parser.parse_args()
    
    IPS_PER_BATCH = args.ips
    WORKERS_PER_IP = args.workers
    INITIAL_IPS = args.initial_ips
    INITIAL_WORKERS_PER_IP = args.initial_workers
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopped.")
