import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

from db_spiders.database import connection

cursor = connection.cursor()

# Check total subjects
cursor.execute('SELECT COUNT(*) as cnt FROM subjects WHERE type="movie"')
r1 = cursor.fetchone()
print(f'Total movie subjects: {r1["cnt"]}')

# Check movies not yet crawled  
cursor.execute('SELECT COUNT(*) as cnt FROM subjects WHERE type="movie" AND douban_id NOT IN (SELECT douban_id FROM movies)')
r2 = cursor.fetchone()
print(f'Movies not yet crawled: {r2["cnt"]}')

# Sample data
cursor.execute('SELECT * FROM subjects WHERE type="movie" LIMIT 5')
samples = cursor.fetchall()
print('\nSample subjects:')
for s in samples:
    print(f'  - ID: {s["douban_id"]}, Type: {s.get("type", "N/A")}')
