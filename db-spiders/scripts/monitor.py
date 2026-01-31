import time
import sys
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

from db_spiders.database import connection

def get_stats():
    connection.commit() # Refresh transaction snapshot
    cursor = connection.cursor()
    
    # Total movies to crawl (from subjects)
    cursor.execute('SELECT COUNT(*) as cnt FROM subjects WHERE type="movie"')
    total = cursor.fetchone()['cnt']
    
    # Already crawled (in movies table)
    cursor.execute('SELECT COUNT(*) as cnt FROM movies')
    crawled = cursor.fetchone()['cnt']
    
    return total, crawled

def main():
    print("📊 Starting Douban Crawler Monitor...")
    print("Press Ctrl+C to stop")
    print("-" * 50)
    
    start_total, start_crawled = get_stats()
    start_time = time.time()
    
    try:
        while True:
            total, current_crawled = get_stats()
            
            # Calculate speed
            elapsed = time.time() - start_time
            newly_crawled = current_crawled - start_crawled
            speed = newly_crawled / elapsed * 60 if elapsed > 0 else 0
            
            # Progress bar
            if total > 0:
                percent = (current_crawled / total) * 100
            else:
                percent = 0
            
            bar_length = 30
            filled_length = int(bar_length * current_crawled // total) if total > 0 else 0
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            
            # Clear line and print status
            sys.stdout.write(f"\r\033[K[{bar}] {percent:.1f}% | {current_crawled}/{total} | Speed: {speed:.1f} req/min")
            sys.stdout.flush()
            
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\nMonitor stopped.")

if __name__ == "__main__":
    main()
