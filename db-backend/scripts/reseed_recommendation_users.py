#!/usr/bin/env python3
"""
清空普通用户并重建推荐训练型用户数据。
"""
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.mysql import close_pool, get_connection, init_pool
from app.db.neo4j import Neo4jConnection
from app.seed.recommendation_users import DEFAULT_REPORT_PATH, reseed_recommendation_users


def parse_args():
    parser = argparse.ArgumentParser(description="重建推荐训练型用户数据")
    parser.add_argument("--dry-run", action="store_true", help="仅生成并校验数据，不写入 MySQL / Neo4j")
    parser.add_argument("--user-count", type=int, default=200, help="生成的用户数量，默认 200")
    parser.add_argument(
        "--persona-set",
        default="default",
        help="使用的 persona 集合，默认 default；也支持逗号分隔的 persona slug",
    )
    parser.add_argument("--seed", type=int, default=20260308, help="保留兼容的种子参数，当前实现为确定性生成")
    parser.add_argument(
        "--llm-provider",
        default="auto",
        choices=("auto", "kimi", "none"),
        help="LLM 提供方，默认 auto",
    )
    parser.add_argument("--report-path", default=DEFAULT_REPORT_PATH, help="质量报告输出路径")
    return parser.parse_args()


def main():
    args = parse_args()

    init_pool()
    conn = get_connection()
    driver = Neo4jConnection.get_driver()
    try:
        report = reseed_recommendation_users(
            conn,
            driver,
            dry_run=args.dry_run,
            user_count=args.user_count,
            persona_set=args.persona_set,
            llm_provider=args.llm_provider,
            report_path=args.report_path,
            clear_existing=True,
            is_mock=False,
            username_prefix="seed_cfkg",
            seed=args.seed,
        )
    finally:
        conn.close()
        close_pool()
        Neo4jConnection.close()

    print("推荐训练型用户数据重建完成")
    print(f"user_count={report['user_count']}")
    print(f"movie_pool_size={report['movie_pool_size']}")
    print(f"rating_count={report['rating_count']}")
    print(f"like_count={report['like_count']}")
    print(f"want_count={report['want_count']}")
    print(f"clear_positive_preference_ratio={report['profile_usability']['clear_positive_preference_ratio']}")
    print(f"time_split_ready_ratio={report['profile_usability']['time_split_ready_ratio']}")
    print(f"report_path={args.report_path}")


if __name__ == "__main__":
    main()
