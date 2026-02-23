#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Douban Person Crawler Monitor
独立监控脚本，实时显示人物爬取进度

使用方法: python scripts/monitor_person.py
"""

import time
import sys
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

from db_spiders.database import connection


def get_stats():
    """获取人物爬取统计数据"""
    connection.commit()  # Refresh transaction snapshot
    cursor = connection.cursor()
    
    # Total persons to crawl (from person_obj)
    cursor.execute('SELECT COUNT(*) as cnt FROM person_obj')
    total = cursor.fetchone()['cnt']
    
    # Already crawled (in person table)
    cursor.execute('SELECT COUNT(*) as cnt FROM person')
    crawled = cursor.fetchone()['cnt']
    
    # Status breakdown
    cursor.execute('''
        SELECT 
            SUM(CASE WHEN status = 0 THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) as in_progress,
            SUM(CASE WHEN status = 2 THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 3 THEN 1 ELSE 0 END) as failed
        FROM person_obj
    ''')
    status_row = cursor.fetchone()
    
    return {
        'total': total,
        'crawled': crawled,
        'pending': status_row['pending'] or 0,
        'in_progress': status_row['in_progress'] or 0,
        'completed': status_row['completed'] or 0,
        'failed': status_row['failed'] or 0,
    }


def main():
    print("📊 Starting Douban Person Crawler Monitor...")
    print("Press Ctrl+C to stop")
    print("-" * 60)
    
    initial_stats = get_stats()
    start_time = time.time()
    start_crawled = initial_stats['crawled']
    last_crawled = start_crawled
    last_time = start_time
    
    try:
        while True:
            stats = get_stats()
            now = time.time()
            
            total = stats['total']
            current_crawled = stats['crawled']
            
            # Calculate speed
            elapsed = now - start_time
            newly_crawled = current_crawled - start_crawled
            avg_speed = newly_crawled / elapsed * 60 if elapsed > 0 else 0
            
            delta_time = now - last_time
            delta_crawled = current_crawled - last_crawled
            crawl_speed = delta_crawled / delta_time * 60 if delta_time > 0 else 0
            remaining = max(0, total - current_crawled)
            
            # Progress bar
            if total > 0:
                percent = (current_crawled / total) * 100
            else:
                percent = 0
            
            bar_length = 25
            filled_length = int(bar_length * current_crawled // total) if total > 0 else 0
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            
            # Dynamic speed unit
            if crawl_speed > 60:
                speed_str = f"{crawl_speed/60:.1f}/s"
            else:
                speed_str = f"{crawl_speed:.1f}/min"
            
            # ETA calculation
            eta_str = "--:--"
            if crawl_speed > 0:
                mins_left = remaining / crawl_speed
                if mins_left > 60:
                    eta_str = f"{mins_left/60:.1f}h"
                else:
                    eta_str = f"{mins_left:.0f}m"
            
            # Status line
            sys.stdout.write(
                f"\r\033[K[{bar}] {percent:.1f}% | "
                f"✅{current_crawled:,}/{total:,} | "
                f"⏳{stats['in_progress']} | "
                f"❌{stats['failed']} | "
                f"Speed: {speed_str} | "
                f"ETA: {eta_str}"
            )
            sys.stdout.flush()
            
            last_crawled, last_time = current_crawled, now
            time.sleep(2)
            
    except KeyboardInterrupt:
        # Print final stats
        stats = get_stats()
        elapsed = time.time() - start_time
        total_new = stats['crawled'] - start_crawled
        
        print(f"\n\n{'='*60}")
        print(f"📊 监控结束 - 最终统计")
        print(f"{'='*60}")
        print(f"运行时长: {elapsed/60:.1f} 分钟")
        print(f"本次爬取: {total_new:,} 条")
        print(f"平均速度: {total_new/elapsed*60:.1f} 条/分钟")
        print(f"\n状态分布:")
        print(f"  ✅ 已完成: {stats['completed']:,}")
        print(f"  ⏳ 进行中: {stats['in_progress']:,}")
        print(f"  📋 待处理: {stats['pending']:,}")
        print(f"  ❌ 失败:   {stats['failed']:,}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
