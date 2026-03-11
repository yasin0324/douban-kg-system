from app.algorithms.base import BaseRecommender
from app.algorithms import evaluator


class FakeAlgo(BaseRecommender):
    name = "fake"
    display_name = "Fake"

    def __init__(self):
        self.calls = []

    def recommend(self, user_id, n=20, exclude_mids=None, exclude_from_training=None):
        exclude_from_training = exclude_from_training or set()
        self.calls.append(
            {
                "user_id": user_id,
                "n": n,
                "exclude_mids": exclude_mids,
                "exclude_from_training": set(exclude_from_training),
            }
        )
        test_mid = next(iter(exclude_from_training))
        return [
            {"mid": test_mid, "score": 0.95, "reason": "hit"},
            {"mid": f"neg-{user_id}-1", "score": 0.5, "reason": "other"},
            {"mid": f"neg-{user_id}-2", "score": 0.4, "reason": "other"},
        ]


def test_split_evaluation_users_is_deterministic():
    evaluation_users = [{"user_id": idx, "test_mid": f"m{idx}", "sampled_negatives": {}} for idx in range(1, 11)]

    validation_a, test_a = evaluator.split_evaluation_users(evaluation_users)
    validation_b, test_b = evaluator.split_evaluation_users(evaluation_users)

    assert validation_a == validation_b
    assert test_a == test_b
    assert len(validation_a) == 2
    assert len(test_a) == 8


def test_evaluate_algorithm_is_deterministic_and_passes_exclude_from_training(monkeypatch):
    monkeypatch.setattr(evaluator, "_diversity_at_k", lambda ranked_list, k: 0.5)
    algo = FakeAlgo()
    evaluation_users = [
        {
            "user_id": 1,
            "test_mid": "m1",
            "sampled_negatives": {
                42: ["neg-1-1", "neg-1-2"],
                52: ["neg-1-1", "neg-1-3"],
            },
        },
        {
            "user_id": 2,
            "test_mid": "m2",
            "sampled_negatives": {
                42: ["neg-2-1", "neg-2-2"],
                52: ["neg-2-1", "neg-2-3"],
            },
        },
    ]

    result_a = evaluator.evaluate_algorithm(
        algo=algo,
        evaluation_users=evaluation_users,
        negative_seeds=[42, 52],
        k_values=[5, 10],
        all_movie_count=100,
        progress_label="fake",
    )
    result_b = evaluator.evaluate_algorithm(
        algo=algo,
        evaluation_users=evaluation_users,
        negative_seeds=[42, 52],
        k_values=[5, 10],
        all_movie_count=100,
        progress_label="fake",
    )

    assert result_a["metrics"] == result_b["metrics"]
    assert result_a["coverage_at_20"] == result_b["coverage_at_20"]
    assert result_a["diversity_at_10"] == result_b["diversity_at_10"]
    assert result_a["metrics"]["5"]["hit_rate"] == 1.0
    assert result_a["metrics"]["10"]["ndcg"] == 1.0
    assert result_a["coverage_at_20"]["mean"] > 0
    assert result_a["diversity_at_10"]["mean"] == 0.5
    assert all(call["exclude_from_training"] == {f"m{call['user_id']}"} for call in algo.calls)


def test_build_markdown_report_includes_ablation_section():
    report = {
        "protocol_version": 2,
        "eval_method": "test",
        "negative_sample_seeds": [42, 52],
        "n_validation_users": 1,
        "n_test_users": 2,
        "results": {
            "kg_path": {
                "display_name": "基于知识图谱路径的推荐",
                "metrics": {
                    "5": {"precision": 0.1, "precision_std": 0.0, "recall": 0.5, "recall_std": 0.0, "ndcg": 0.4, "ndcg_std": 0.0, "hit_rate": 0.5, "hit_rate_std": 0.0},
                    "10": {"precision": 0.1, "precision_std": 0.0, "recall": 0.6, "recall_std": 0.0, "ndcg": 0.5, "ndcg_std": 0.0, "hit_rate": 0.6, "hit_rate_std": 0.0},
                    "20": {"precision": 0.1, "precision_std": 0.0, "recall": 0.7, "recall_std": 0.0, "ndcg": 0.6, "ndcg_std": 0.0, "hit_rate": 0.7, "hit_rate_std": 0.0},
                },
                "coverage_at_20": {"mean": 0.2, "std": 0.01},
                "diversity_at_10": {"mean": 0.3, "std": 0.02},
                "avg_time_seconds": 0.1234,
                "best_params": {"actor_weight": 0.6},
                "ablations": {
                    "1-hop": {
                        "metrics": {
                            "10": {"recall": 0.4, "recall_std": 0.0, "ndcg": 0.3, "ndcg_std": 0.0, "hit_rate": 0.4, "hit_rate_std": 0.0}
                        },
                        "params": {"enable_two_hop": False},
                    }
                },
            }
        },
    }

    markdown = evaluator.build_markdown_report(report, include_ablations=True)

    assert "## Ablations" in markdown
    assert "1-hop" in markdown
    assert "actor_weight" in markdown


def test_tune_algorithm_progress_labels_include_grid_index(monkeypatch):
    class TunableFakeAlgo(FakeAlgo):
        display_name = "Tunable Fake"

        @classmethod
        def parameter_grid(cls):
            return [{"alpha": 0.1}, {"alpha": 0.2}]

        def set_params(self, **params):
            self.params = params

    labels = []

    def fake_evaluate_algorithm(**kwargs):
        labels.append(kwargs["progress_label"])
        return {
            "metrics": {
                "10": {"ndcg": 0.1, "hit_rate": 0.1},
                "5": {"ndcg": 0.1},
            }
        }

    monkeypatch.setattr(evaluator, "evaluate_algorithm", fake_evaluate_algorithm)

    evaluator.tune_algorithm(
        algo_class=TunableFakeAlgo,
        validation_users=[{"user_id": 1, "test_mid": "m1", "sampled_negatives": {}}],
        all_movie_count=100,
    )

    assert labels == [
        "  验证[1/2] Tunable Fake",
        "  验证[2/2] Tunable Fake",
    ]
