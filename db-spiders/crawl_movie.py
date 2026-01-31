#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Concurrent Playwright-based crawler for Douban movies
Uses multiple browser instances for faster crawling
"""

import os
import re
import sys
import time
import random
import threading
from queue import Queue
from playwright.sync_api import sync_playwright
BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)
from db_spiders.database import connection
from db_spiders import validator

# Thread-safe lock for database operations
db_lock = threading.Lock()
# Statistics
stats = {
    'inserted': 0,
    'updated': 0,
    'skipped': 0,
    'failed': 0,
    'not_found': 0
}
stats_lock = threading.Lock()

MOVIE_FIELDS = [
    'douban_id', 'type', 'slug', 'name', 'alias', 'cover', 'year',
    'genres', 'regions', 'languages', 'official_site', 'mins', 'imdb_id',
    'tags', 'storyline', 'douban_score', 'douban_votes', 'release_date',
    'directors', 'actors', 'actor_ids', 'director_ids'
]

def parse_ids_text(text):
    """Parse ids from comma/space/newline separated text"""
    if not text:
        return []
    parts = re.split(r'[\s,]+', text.strip())
    ids = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            ids.append(int(part))
    return ids

def load_ids_from_file(path):
    """Load ids from file (supports comments and mixed separators)"""
    ids = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            ids.extend(parse_ids_text(line))
    return ids

def dedupe_ids(ids):
    """Deduplicate ids while preserving order"""
    seen = set()
    result = []
    for movie_id in ids:
        if movie_id in seen:
            continue
        seen.add(movie_id)
        result.append(movie_id)
    return result

def get_uncrawled_movies(limit=None):
    """Get movies that haven't been crawled yet"""
    cursor = connection.cursor()
    sql = '''SELECT douban_id FROM subjects 
             WHERE type="movie" 
             AND douban_id NOT IN (SELECT douban_id FROM movies) 
             ORDER BY douban_id DESC'''
    params = []
    if limit is not None:
        sql += ' LIMIT %s'
        params.append(limit)
    if params:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql)
    return [row['douban_id'] for row in cursor.fetchall()]

def extract_movie_data(page, douban_id):
    """Extract movie data from page"""
    try:
        # Wait for content to load
        page.wait_for_selector('#content', timeout=10000)
        
        data = {'douban_id': douban_id}
        
        # Extract basic info
        try:
            data['name'] = page.locator('h1 span[property="v:itemreviewed"]').inner_text()
        except:
            data['name'] = page.locator('title').inner_text().replace(' (豆瓣)', '').strip()
        
        # Year
        try:
            year_text = page.locator('span.year').inner_text()
            data['year'] = validator.match_year(year_text)
        except:
            data['year'] = None
        
        # Type
        try:
            episodes = page.locator('span:text("集数:")').count()
            data['type'] = 'tv' if episodes > 0 else 'movie'
        except:
            data['type'] = 'movie'
        
        # Cover
        try:
            cover = page.locator('img[rel="v:image"]').get_attribute('src')
            if cover and 'default' not in cover:
                data['cover'] = cover.replace('spst', 'lpst').replace('mpic', 'lpic')
            else:
                data['cover'] = None
        except:
            data['cover'] = None
        
        # Directors
        try:
            directors = page.locator('a[rel="v:directedBy"]').all_text_contents()
            data['directors'] = '/'.join(directors) if directors else None
        except:
            data['directors'] = None
        
        # Director IDs
        try:
            director_links = page.locator('a[rel="v:directedBy"]').all()
            director_ids = []
            director_names = []
            for link in director_links:
                href = link.get_attribute('href')
                name = link.inner_text()
                if href:
                    did = href.split('/')[-2]
                    director_ids.append(f"{name}:{did}")
                    director_names.append(name)
            data['director_ids'] = '|'.join(director_ids) if director_ids else None
            if not data['directors']:
                data['directors'] = '/'.join(director_names) if director_names else None
        except:
            data['director_ids'] = None
        
        # Actors
        try:
            actors = page.locator('a[rel="v:starring"]').all_text_contents()
            data['actors'] = '/'.join(actors) if actors else None
        except:
            data['actors'] = None
        
        # Actor IDs
        try:
            actor_links = page.locator('a[rel="v:starring"]').all()
            actor_ids = []
            actor_names = []
            for link in actor_links:
                href = link.get_attribute('href')
                name = link.inner_text()
                if href:
                    aid = href.split('/')[-2]
                    actor_ids.append(f"{name}:{aid}")
                    actor_names.append(name)
            data['actor_ids'] = '|'.join(actor_ids) if actor_ids else None
            if not data['actors']:
                data['actors'] = '/'.join(actor_names) if actor_names else None
        except:
            data['actor_ids'] = None
        
        # Genres
        try:
            genres = page.locator('span[property="v:genre"]').all_text_contents()
            data['genres'] = '/'.join(genres) if genres else None
        except:
            data['genres'] = None
        
        # Regions
        try:
            info_text = page.locator('#info').inner_text()
            for line in info_text.split('\n'):
                if '制片国家/地区:' in line:
                    data['regions'] = line.split('制片国家/地区:')[1].strip()
                    break
            else:
                data['regions'] = None
        except:
            data['regions'] = None
        
        # Languages
        try:
            info_text = page.locator('#info').inner_text()
            for line in info_text.split('\n'):
                if '语言:' in line:
                    data['languages'] = line.split('语言:')[1].strip()
                    break
            else:
                data['languages'] = None
        except:
            data['languages'] = None
        
        # Release date
        try:
            release_dates = page.locator('span[property="v:initialReleaseDate"]').all()
            if release_dates:
                date_str = release_dates[0].get_attribute('content')
                data['release_date'] = validator.str_to_date(validator.match_date(date_str))
            else:
                data['release_date'] = None
        except:
            data['release_date'] = None
        
        # Runtime
        try:
            runtime = page.locator('span[property="v:runtime"]').get_attribute('content')
            data['mins'] = int(runtime) if runtime else None
        except:
            data['mins'] = None
        
        # Alias
        try:
            info_text = page.locator('#info').inner_text()
            for line in info_text.split('\n'):
                if '又名:' in line:
                    data['alias'] = validator.process_slash_str(line.split('又名:')[1].strip())
                    break
            else:
                data['alias'] = None
        except:
            data['alias'] = None
        
        # IMDb ID
        try:
            imdb_link = page.locator('a:has-text("IMDb")').first
            href = imdb_link.get_attribute('href')
            if href:
                data['imdb_id'] = href.strip().split('?')[0][26:]
            else:
                data['imdb_id'] = None
        except:
            data['imdb_id'] = None
        
        # Score
        try:
            score = page.locator('strong[property="v:average"]').inner_text()
            data['douban_score'] = float(score) if score else None
        except:
            data['douban_score'] = None
        
        # Votes
        try:
            votes = page.locator('span[property="v:votes"]').inner_text()
            data['douban_votes'] = int(votes) if votes else None
        except:
            data['douban_votes'] = None
        
        # Tags
        try:
            tags = page.locator('div.tags-body a').all_text_contents()
            data['tags'] = '/'.join(tags) if tags else None
        except:
            data['tags'] = None
        
        # Storyline
        try:
            storyline = page.locator('span.all.hidden').inner_text()
            data['storyline'] = storyline.strip()
        except:
            try:
                storyline_parts = page.locator('span[property="v:summary"]').all_text_contents()
                data['storyline'] = '\n'.join([p.strip() for p in storyline_parts])
            except:
                data['storyline'] = None
        
        # Official site
        try:
            info_text = page.locator('#info').inner_text()
            for line in info_text.split('\n'):
                if '官方网站:' in line:
                    data['official_site'] = line.split('官方网站:')[1].strip()
                    break
            else:
                data['official_site'] = None
        except:
            data['official_site'] = None
        
        # Generate slug
        from db_spiders.util import shorturl
        try:
            data['slug'] = shorturl(str(douban_id))
        except:
            data['slug'] = None
        
        return data
        
    except Exception as e:
        return None

def save_to_database(data, allow_update=False):
    """Save movie data to database (thread-safe)"""
    with db_lock:
        cursor = connection.cursor()
        
        # Check if already exists
        cursor.execute("SELECT douban_id FROM movies WHERE douban_id = %s", (data['douban_id'],))
        exists = cursor.fetchone()
        
        if exists:
            if not allow_update:
                return "skipped"
            update_fields = [f for f in MOVIE_FIELDS if f != 'douban_id']
            set_clause = ', '.join([f"{f} = %s" for f in update_fields])
            values = [data.get(f) for f in update_fields] + [data['douban_id']]
            sql = f"UPDATE movies SET {set_clause} WHERE douban_id = %s"
            try:
                cursor.execute(sql, values)
                connection.commit()
                return "updated"
            except Exception:
                connection.rollback()
                return "failed"
        
        # Insert new movie
        values = [data.get(f) for f in MOVIE_FIELDS]
        placeholders = ', '.join(['%s'] * len(MOVIE_FIELDS))
        field_names = ', '.join(MOVIE_FIELDS)
        
        sql = f"INSERT INTO movies ({field_names}) VALUES ({placeholders})"
        
        try:
            cursor.execute(sql, values)
            connection.commit()
            return "inserted"
        except Exception:
            connection.rollback()
            return "failed"

def worker_thread(worker_id, movie_queue, delay_range, headless=True, update_existing=False):
    """Worker thread that processes movies from the queue"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN'
        )
        page = context.new_page()
        
        try:
            while True:
                try:
                    # Get next movie from queue (non-blocking with timeout)
                    movie_id = movie_queue.get(timeout=1)
                    if movie_id is None:  # Sentinel value to stop
                        break
                    
                    url = f'https://movie.douban.com/subject/{movie_id}/'
                    print(f"[Worker-{worker_id}] Crawling: {url}")
                    
                    retry_count = 0
                    max_retries = 3
                    success = False
                    
                    while retry_count < max_retries and not success:
                        try:
                            if retry_count > 0:
                                print(f"[Worker-{worker_id}]   Retrying {retry_count}...")
                            
                            # Navigate to page with longer timeout
                            response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
                            
                            # Wait for stability
                            try:
                                page.wait_for_load_state('networkidle', timeout=3000)
                            except:
                                pass
                            
                            # Check HTTP status
                            if response and response.status == 404:
                                print(f"[Worker-{worker_id}]   ⚠ HTTP 404: Movie {movie_id} not found")
                                with stats_lock:
                                    stats['not_found'] += 1
                                break # Don't retry real 404s
                            
                            # Check title for anti-scraping
                            try:
                                title = page.title()
                                if '登录' in title or '验证' in title or '禁止访问' in title:
                                    print(f"[Worker-{worker_id}]   ⚠ Anti-scraping detected, pausing...")
                                    time.sleep(random.uniform(10, 20))
                                    raise Exception("Anti-scraping")
                            except:
                                pass

                            # Check content existence logic
                            has_content = False
                            try:
                                page.wait_for_selector('#content', timeout=5000)
                                if page.locator('h1 span[property="v:itemreviewed"]').count() > 0:
                                    has_content = True
                            except:
                                pass
                            
                            # Fallback check
                            if not has_content:
                                content = page.content()
                                if '页面不存在' in content or ('404' in content and len(content) < 5000):
                                    print(f"[Worker-{worker_id}]   ⚠ Page not found (Body check): {movie_id}")
                                    with stats_lock:
                                        stats['not_found'] += 1
                                    break
                            
                            # Extract data
                            data = extract_movie_data(page, movie_id)
                            
                            if data:
                                # Save to database
                                result = save_to_database(data, allow_update=update_existing)
                                if result == "inserted":
                                    print(f"[Worker-{worker_id}]   ✓ Saved: {data.get('name', 'Unknown')} (ID: {movie_id})")
                                    with stats_lock:
                                        stats['inserted'] += 1
                                elif result == "updated":
                                    print(f"[Worker-{worker_id}]   ↻ Updated: {data.get('name', 'Unknown')} (ID: {movie_id})")
                                    with stats_lock:
                                        stats['updated'] += 1
                                elif result == "skipped":
                                    print(f"[Worker-{worker_id}]   - Skipped (exists): {movie_id}")
                                    with stats_lock:
                                        stats['skipped'] += 1
                                else:
                                    print(f"[Worker-{worker_id}]   ✗ Failed to save")
                                    with stats_lock:
                                        stats['failed'] += 1
                                success = True
                            else:
                                print(f"[Worker-{worker_id}]   ✗ Failed to extract data")
                                raise Exception("Extraction failed")
                                
                        except Exception as e:
                            print(f"[Worker-{worker_id}]   ✗ Error (Attempt {retry_count+1}): {e}")
                            retry_count += 1
                            time.sleep(random.uniform(2, 5))
                            
                    if not success and retry_count >= max_retries:
                         print(f"[Worker-{worker_id}]   ✗ Final failure for {movie_id}")
                         with stats_lock:
                             stats['failed'] += 1
                        
                    # Random delay
                    delay = random.uniform(delay_range[0], delay_range[1])
                    time.sleep(delay)
                    
                except:
                    # Queue empty or other error outside loop
                    if movie_queue.empty():
                        break
                    else:
                         continue
                finally:
                    if 'movie_id' in locals() and movie_id is not None:
                        try:
                            movie_queue.task_done()
                        except:
                            pass
                    
        finally:
            browser.close()

def crawl_movies_concurrent(num_workers=2, headless=True, delay_range=(2, 5), max_movies=None, movie_ids=None, update_existing=False):
    """
    Concurrent crawling with multiple browser instances
    
    Args:
        num_workers: Number of concurrent browser instances
        headless: Run browsers in headless mode
        delay_range: Random delay between requests (min, max) in seconds
        max_movies: Maximum number of movies to crawl (None = all)
        movie_ids: Specific movie ids to crawl (None = use subjects table)
        update_existing: Update existing records if already present
    """
    # Get uncrawled movies or use provided ids
    if movie_ids is None:
        movie_ids = get_uncrawled_movies(limit=max_movies)
        mode = "subjects (uncrawled)"
    else:
        movie_ids = dedupe_ids(movie_ids)
        mode = "explicit ids"
    
    if not movie_ids:
        print("No movies to crawl!")
        return
    
    total = len(movie_ids)
    print(f"\n{'='*60}")
    print(f"🚀 CONCURRENT CRAWLING MODE")
    print(f"{'='*60}")
    print(f"Movies to crawl: {total}")
    print(f"Mode: {mode}")
    print(f"Concurrent workers: {num_workers}")
    print(f"Headless mode: {headless}")
    print(f"Delay range: {delay_range[0]}-{delay_range[1]} seconds")
    print(f"Update existing: {update_existing}")
    print(f"{'='*60}\n")
    
    # Create queue and add all movie IDs
    movie_queue = Queue()
    for movie_id in movie_ids:
        movie_queue.put(movie_id)
    
    # Start worker threads
    threads = []
    start_time = time.time()
    
    for i in range(num_workers):
        thread = threading.Thread(
            target=worker_thread,
            args=(i+1, movie_queue, delay_range, headless, update_existing)
        )
        thread.start()
        threads.append(thread)
    
    # Wait for all tasks to complete
    movie_queue.join()
    
    # Send stop signal to all workers
    for _ in range(num_workers):
        movie_queue.put(None)
    
    # Wait for all threads to finish
    for thread in threads:
        thread.join()
    
    elapsed_time = time.time() - start_time
    
    print(f"\n{'='*60}")
    print(f"✅ Crawling completed!")
    print(f"{'='*60}")
    print(f"Total movies: {total}")
    print(f"Inserted: {stats['inserted']}")
    print(f"Updated: {stats['updated']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Failed: {stats['failed']}")
    print(f"Not found (404): {stats['not_found']}")
    print(f"Time elapsed: {elapsed_time/60:.1f} minutes")
    print(f"Average: {elapsed_time/total:.1f} seconds/movie")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Concurrent Douban movie crawler using Playwright')
    parser.add_argument('--workers', type=int, default=2, help='Number of concurrent browser instances (default: 2)')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    parser.add_argument('--visible', action='store_true', help='Run with visible browsers')
    parser.add_argument('--max', type=int, default=None, help='Maximum number of movies to crawl')
    parser.add_argument('--delay-min', type=int, default=2, help='Minimum delay between requests (seconds)')
    parser.add_argument('--delay-max', type=int, default=5, help='Maximum delay between requests (seconds)')
    parser.add_argument('--test', action='store_true', help='Test mode: crawl 10 movies with 2 workers')
    parser.add_argument('--ids', type=str, default=None, help='Comma/space separated douban_id list')
    parser.add_argument('--ids-file', type=str, default=None, help='Path to file with douban_id list')
    parser.add_argument('--update', action='store_true', help='Update existing movies if already in DB')
    
    args = parser.parse_args()
    
    if args.test:
        print("\n🔍 TEST MODE: Crawling 10 movies with 2 workers\n")
        crawl_movies_concurrent(
            num_workers=2,
            headless=not args.visible,
            delay_range=(2, 4),
            max_movies=10
        )
    else:
        headless = args.headless or not args.visible
        selected_ids = []
        if args.ids:
            selected_ids.extend(parse_ids_text(args.ids))
        if args.ids_file:
            selected_ids.extend(load_ids_from_file(args.ids_file))
        if selected_ids:
            selected_ids = dedupe_ids(selected_ids)
        crawl_movies_concurrent(
            num_workers=args.workers,
            headless=headless,
            delay_range=(args.delay_min, args.delay_max),
            max_movies=args.max,
            movie_ids=selected_ids if selected_ids else None,
            update_existing=args.update
        )
