#!/usr/bin/env python3
"""
导出 CFKG 训练数据集。
"""
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.algorithms.cfkg.artifacts import DEFAULT_DATASET_ROOT
from app.algorithms.cfkg.dataset import export_cfkg_dataset
from app.db.mysql import close_pool, get_connection, init_pool
from app.db.neo4j import Neo4jConnection


def parse_args():
    parser = argparse.ArgumentParser(description="导出 CFKG 数据集")
    parser.add_argument(
        "--dataset-root",
        default=str(DEFAULT_DATASET_ROOT),
        help="数据集输出根目录，默认 tmp/cfkg/datasets",
    )
    parser.add_argument("--version", default=None, help="数据集版本名，默认时间戳")
    return parser.parse_args()


def main():
    args = parse_args()
    init_pool()
    conn = get_connection()
    driver = Neo4jConnection.get_driver()
    try:
        result = export_cfkg_dataset(
            conn,
            driver=driver,
            dataset_root=args.dataset_root,
            version=args.version,
        )
    finally:
        conn.close()
        close_pool()
        Neo4jConnection.close()

    metadata = result["metadata"]
    print("CFKG 数据集导出完成")
    print(f"dataset_dir={result['dataset_dir']}")
    print(f"entity_count={metadata['entity_count']}")
    print(f"relation_count={metadata['relation_count']}")
    print(f"train_triple_count={metadata['train_triple_count']}")
    print(f"eval_triple_count={metadata['eval_triple_count']}")
    print(f"holdout_user_count={metadata['holdout_user_count']}")


if __name__ == "__main__":
    main()

