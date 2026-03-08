#!/usr/bin/env python3
"""
训练 CFKG 模型。
"""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.algorithms.cfkg.artifacts import DEFAULT_MODEL_ROOT
from app.algorithms.cfkg.training import (
    TrainingConfig,
    default_experiment_configs,
    train_cfkg_model,
)


def parse_args():
    parser = argparse.ArgumentParser(description="训练 CFKG 模型")
    parser.add_argument("--dataset-dir", default=None, help="CFKG 数据集目录，默认 latest")
    parser.add_argument("--output-dir", default=str(DEFAULT_MODEL_ROOT), help="模型输出目录")
    parser.add_argument("--embedding-dim", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--margin", type=float, default=1.0)
    parser.add_argument("--hard-negative-weight", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=20260308)
    parser.add_argument("--device", default=None, help="可选: cpu / cuda / mps")
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="关闭训练进度条输出",
    )
    parser.add_argument(
        "--run-default-matrix",
        action="store_true",
        help="运行内置实验矩阵（embedding_dim / epochs / learning_rate / hard_negative_weight）",
    )
    parser.add_argument(
        "--experiment-limit",
        type=int,
        default=None,
        help="可选：限制实验矩阵前 N 组配置，便于快速试跑",
    )
    return parser.parse_args()


def _build_base_config(args) -> TrainingConfig:
    return TrainingConfig(
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
        embedding_dim=args.embedding_dim,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        margin=args.margin,
        hard_negative_weight=args.hard_negative_weight,
        seed=args.seed,
        device=args.device,
        show_progress=not args.no_progress,
    )


def _print_result(result):
    print("CFKG 模型训练完成")
    print(f"dataset_dir={result['dataset_dir']}")
    print(f"model_path={result['model_path']}")
    print(f"device={result['device']}")
    print(f"final_loss={result['metrics']['final_loss']}")
    print(f"train_triple_count={result['metrics']['train_triple_count']}")
    print(f"holdout_user_count={result['metrics']['holdout_user_count']}")


def _run_default_matrix(args):
    base_config = _build_base_config(args)
    configs = default_experiment_configs(base_config)
    if args.experiment_limit is not None:
        configs = configs[:max(args.experiment_limit, 0)]

    results = []
    for index, config in enumerate(configs, start=1):
        print(
            f"[{index}/{len(configs)}] "
            f"embedding_dim={config.embedding_dim} "
            f"epochs={config.epochs} "
            f"learning_rate={config.learning_rate} "
            f"hard_negative_weight={config.hard_negative_weight}"
        )
        result = train_cfkg_model(config)
        results.append({
            "output_dir": result["output_dir"],
            "model_path": result["model_path"],
            "dataset_dir": result["dataset_dir"],
            "device": result["device"],
            "config": {
                "embedding_dim": config.embedding_dim,
                "epochs": config.epochs,
                "batch_size": config.batch_size,
                "learning_rate": config.learning_rate,
                "margin": config.margin,
                "hard_negative_weight": config.hard_negative_weight,
                "seed": config.seed,
                "device": config.device,
            },
            "metrics": result["metrics"],
        })

    summary_path = Path(args.output_dir) / "experiment_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"matrix_summary={summary_path}")


def main():
    args = parse_args()
    if args.run_default_matrix:
        _run_default_matrix(args)
        return

    result = train_cfkg_model(_build_base_config(args))

    _print_result(result)


if __name__ == "__main__":
    main()
