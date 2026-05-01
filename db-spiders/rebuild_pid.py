#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
rebuild_pid.py

Extracts person IDs from movies.actor_ids and movies.director_ids
and populates the person_obj table for crawl_person.py to crawl.

Usage:
    python rebuild_pid.py
"""

import sys
import os

BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)

import db_spiders.database as db

cursor = db.connection.cursor()


def extract_person_ids():
    """
    Extract person IDs from actor_ids and director_ids fields in movies table
    
    Format of actor_ids/director_ids: "姓名:ID|姓名:ID|..."
    Example: "周星驰:1048026|吴孟达:1012521"
    """
    print("Starting to extract person IDs from movies table...")
    
    # Get all movies with actor_ids or director_ids
    sql = """
    SELECT douban_id, actor_ids, director_ids 
    FROM movies 
    WHERE actor_ids IS NOT NULL OR director_ids IS NOT NULL
    """
    
    cursor.execute(sql)
    movies = cursor.fetchall()
    
    print(f"Found {len(movies)} movies with person information")
    
    person_dict = {}  # Store unique person_id -> name mapping
    
    for movie in movies:
        # Process actor_ids
        if movie.get('actor_ids'):
            actor_ids = movie['actor_ids']
            # Split by | to get individual "name:id" pairs
            pairs = actor_ids.split('|')
            for pair in pairs:
                if ':' in pair:
                    name, person_id = pair.split(':', 1)
                    if person_id.isdigit():
                        person_dict[person_id] = name.strip()
        
        # Process director_ids
        if movie.get('director_ids'):
            director_ids = movie['director_ids']
            pairs = director_ids.split('|')
            for pair in pairs:
                if ':' in pair:
                    name, person_id = pair.split(':', 1)
                    if person_id.isdigit():
                        person_dict[person_id] = name.strip()
    
    print(f"Extracted {len(person_dict)} unique person IDs")
    
    # Insert into person_obj table
    inserted_count = 0
    skipped_count = 0
    
    for person_id, name in person_dict.items():
        try:
            # Check if already exists
            check_sql = "SELECT id FROM person_obj WHERE person_id = %s"
            cursor.execute(check_sql, (person_id,))
            existing = cursor.fetchone()
            
            if not existing:
                # Insert new person
                insert_sql = "INSERT INTO person_obj (person_id, name) VALUES (%s, %s)"
                cursor.execute(insert_sql, (person_id, name))
                db.connection.commit()
                inserted_count += 1
                
                if inserted_count % 100 == 0:
                    print(f"Inserted {inserted_count} persons...")
            else:
                skipped_count += 1
                
        except Exception as e:
            print(f"Error inserting person {person_id} ({name}): {e}")
            db.connection.rollback()
    
    print(f"\nCompleted!")
    print(f"  - Inserted: {inserted_count} new persons")
    print(f"  - Skipped: {skipped_count} existing persons")
    print(f"  - Total unique persons: {len(person_dict)}")
    

if __name__ == '__main__':
    try:
        extract_person_ids()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
