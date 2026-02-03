import os
import sys

# Add parent directory to path to import db_spiders
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_spiders.database import connection

def reset_all_locks():
    with connection.cursor() as cursor:
        print("Checking lock status...")
        cursor.execute("SELECT COUNT(*) as c FROM subjects WHERE crawl_status=1")
        count = cursor.fetchone()['c']
        print(f"Found {count} locked tasks (crawl_status=1).")
        
        if count > 0:
            print("Resetting ALL locks...")
            cursor.execute("UPDATE subjects SET crawl_status=0, crawl_locked_at=NULL, crawl_worker=NULL WHERE crawl_status=1")
            connection.commit()
            print("Reset complete.")
        else:
            print("No locks to reset.")

if __name__ == "__main__":
    reset_all_locks()
