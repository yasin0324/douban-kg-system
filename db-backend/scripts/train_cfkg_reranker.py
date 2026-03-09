#!/usr/bin/env python3
"""
训练 CFKG 轻量学习排序器。
"""
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.algorithms.cfkg.artifacts import DEFAULT_RERANKER_PATH
from app.algorithms.cfkg.reranker_training import RerankerTrainingConfig, train_cfkg_reranker


def parse_args():
    parser = argparse.ArgumentParser(description="训练 CFKG 轻量学习排序器")
    parser.add_argument("--output-path", default=str(DEFAULT_RERANKER_PATH))
    parser.add_argument("--user-limit", type=int, default=200)
    parser.add_argument("--recommendation-limit", type=int, default=50)
    parser.add_argument("--timeout-ms", type=int, default=2500)
    parser.add_argument("--iterations", type=int, default=800)
    parser.add_argument("--learning-rate", type=float, default=0.08)
    parser.add_argument("--l2", type=float, default=0.01)
    return parser.parse_args()


async def main():
    args = parse_args()
    result = await train_cfkg_reranker(
        RerankerTrainingConfig(
            output_path=args.output_path,
            user_limit=args.user_limit,
            recommendation_limit=args.recommendation_limit,
            timeout_ms=args.timeout_ms,
            iterations=args.iterations,
            learning_rate=args.learning_rate,
            l2=args.l2,
        )
    )
    print("CFKG reranker 训练完成")
    print(f"output_path={result['output_path']}")
    for key, value in result["metrics"].items():
        print(f"{key}={value}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
