import json
import sys

import app.algorithms as algorithms_module
from app.algorithms.base import BaseRecommender
from app.algorithms import evaluator


class FakeAlgo(BaseRecommender):
    name = "fake"
    display_name = "Fake"

    def __init__(self):
        self.calls = []
        self.clear_calls = 0

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

    def clear_runtime_caches(self):
        self.clear_calls += 1


def _fake_eval_summary() -> dict:
    return {
        "metrics": {
            "5": {"precision": 0.1, "precision_std": 0.0, "recall": 0.5, "recall_std": 0.0, "ndcg": 0.4, "ndcg_std": 0.0, "hit_rate": 0.5, "hit_rate_std": 0.0},
            "10": {"precision": 0.1, "precision_std": 0.0, "recall": 0.6, "recall_std": 0.0, "ndcg": 0.5, "ndcg_std": 0.0, "hit_rate": 0.6, "hit_rate_std": 0.0},
            "20": {"precision": 0.1, "precision_std": 0.0, "recall": 0.7, "recall_std": 0.0, "ndcg": 0.6, "ndcg_std": 0.0, "hit_rate": 0.7, "hit_rate_std": 0.0},
        },
        "per_seed": {},
        "coverage_at_20": {"mean": 0.2, "std": 0.01},
        "diversity_at_10": {"mean": 0.3, "std": 0.02},
        "time_seconds": 1.23,
        "avg_time_seconds": 0.1234,
        "n_users": 2,
    }


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


def test_evaluate_algorithm_clears_runtime_caches_per_user(monkeypatch):
    monkeypatch.setattr(evaluator, "_diversity_at_k", lambda ranked_list, k: 0.0)
    algo = FakeAlgo()
    evaluation_users = [
        {
            "user_id": 1,
            "test_mid": "m1",
            "sampled_negatives": {42: ["neg-1-1", "neg-1-2"]},
        },
        {
            "user_id": 2,
            "test_mid": "m2",
            "sampled_negatives": {42: ["neg-2-1", "neg-2-2"]},
        },
    ]

    evaluator.evaluate_algorithm(
        algo=algo,
        evaluation_users=evaluation_users,
        negative_seeds=[42],
        k_values=[5],
        all_movie_count=100,
        progress_label="fake",
    )

    assert algo.clear_calls == len(evaluation_users) + 1


def test_build_markdown_report_includes_ablation_section():
    report = {
        "protocol_version": 2,
        "eval_method": "test",
        "user_source": "public",
        "user_source_display": "公开豆瓣用户（douban_public_*)",
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
    assert "HR@5" in markdown
    assert "NDCG@5" in markdown
    assert "Recall@5" not in markdown
    assert "Precision@5" not in markdown
    assert "Recall@K 与 Hit Rate@K 数值恒等" in markdown
    assert "公开豆瓣用户（douban_public_*)" in markdown


def test_user_source_helpers_cover_public_filter():
    query, params = evaluator._ratings_query_for_user_source("public")

    assert "JOIN users u ON u.id = r.user_id" in query
    assert "u.username LIKE %s" in query
    assert params == ("douban_public_%",)
    assert evaluator.describe_user_source("seed_cfkg") == "历史 mock 用户（seed_cfkg_*)"


def test_build_evaluation_users_respects_num_negatives(monkeypatch):
    ratings_rows = [
        {"user_id": 1, "mid": "m1", "rating": 5.0, "rated_at": "2026-04-01"},
        {"user_id": 1, "mid": "m2", "rating": 4.0, "rated_at": "2026-04-02"},
        {"user_id": 1, "mid": "m3", "rating": 2.0, "rated_at": "2026-04-03"},
    ]
    movie_rows = [{"douban_id": f"m{idx}"} for idx in range(1, 12)]

    class FakeCursor:
        def __init__(self):
            self._result = None

        def execute(self, query, params=()):
            if "FROM user_movie_ratings" in query:
                self._result = ratings_rows
            elif "SELECT douban_id FROM movies" in query:
                self._result = movie_rows
            else:
                raise AssertionError(query)

        def fetchall(self):
            return list(self._result or [])

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(evaluator, "get_connection", lambda: FakeConn())

    users, movie_count = evaluator.build_evaluation_users(
        user_source="public",
        num_negatives=5,
        negative_seeds=[42, 52],
    )

    assert movie_count == 11
    assert len(users) == 1
    assert sorted(users[0]["sampled_negatives"]) == [42, 52]
    assert all(len(rows) == 5 for rows in users[0]["sampled_negatives"].values())


def test_prewarm_embedding_artifacts_invokes_kg_embed_preload(monkeypatch, capsys):
    from app.algorithms.kg_embed import KGEmbedRecommender

    calls = []

    def fake_preload(cls, *, allow_training=None):
        calls.append(allow_training)
        return {"core": True, "expanded": True}

    monkeypatch.setattr(
        KGEmbedRecommender,
        "preload_artifacts",
        classmethod(fake_preload),
    )

    readiness = evaluator._prewarm_embedding_artifacts()
    captured = capsys.readouterr()

    assert readiness == {"core": True, "expanded": True}
    assert calls == [None]
    assert "预热 KG-Embed 嵌入工件" in captured.out
    assert "KG-Embed 预热完成" in captured.out


def test_parse_args_defaults_to_all(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["evaluator.py"])

    args = evaluator.parse_args()

    assert args.user_source == "all"
    assert args.num_negatives == evaluator.NUM_NEGATIVES


def test_parse_args_accepts_public(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["evaluator.py", "--user-source", "public"])

    args = evaluator.parse_args()

    assert args.user_source == "public"


def test_parse_args_accepts_algorithm_subset(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["evaluator.py", "--algorithms", "kg_path"])

    args = evaluator.parse_args()

    assert args.algorithms == ["kg_path"]


def test_parse_args_accepts_num_negatives(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["evaluator.py", "--num-negatives", "499"])

    args = evaluator.parse_args()

    assert args.num_negatives == 499


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
        negative_seeds=[42, 52],
    )

    assert labels == [
        "  验证[1/2] Tunable Fake",
        "  验证[2/2] Tunable Fake",
    ]


def test_evaluate_suite_limits_selected_algorithms(monkeypatch):
    class SelectedAlgo(FakeAlgo):
        name = "kg_path"
        display_name = "KG Path"

    class OtherAlgo(FakeAlgo):
        name = "content"
        display_name = "Other"

    monkeypatch.setattr(
        algorithms_module,
        "ALGORITHMS",
        {"kg_path": SelectedAlgo, "content": OtherAlgo},
    )
    monkeypatch.setattr(algorithms_module, "ALGORITHM_NAMES", ["kg_path", "content"])
    builder_calls = []
    monkeypatch.setattr(
        evaluator,
        "build_evaluation_users",
        lambda user_source="all", num_negatives=evaluator.NUM_NEGATIVES, negative_seeds=None: (
            builder_calls.append(
                {
                    "user_source": user_source,
                    "num_negatives": num_negatives,
                    "negative_seeds": list(negative_seeds or []),
                }
            )
            or [{"user_id": 1, "test_mid": "m1", "sampled_negatives": {seed: ["n1"] for seed in evaluator.NEGATIVE_SAMPLE_SEEDS}}],
            100,
        ),
    )
    monkeypatch.setattr(evaluator, "split_evaluation_users", lambda evaluation_users: ([], evaluation_users))
    prewarm_calls = []
    monkeypatch.setattr(
        evaluator,
        "_prewarm_embedding_artifacts",
        lambda: prewarm_calls.append(True) or {"core": True, "expanded": True},
    )
    monkeypatch.setattr(evaluator, "evaluate_algorithm", lambda **kwargs: _fake_eval_summary())

    report_bundle = evaluator.evaluate_suite(
        user_source="public",
        algorithms=["kg_path"],
        num_negatives=499,
    )

    assert list(report_bundle["main"]["results"]) == ["kg_path"]
    assert list(report_bundle["legacy"]["results"]) == ["kg_path"]
    assert report_bundle["main"]["selected_algorithms"] == ["kg_path"]
    assert report_bundle["legacy"]["selected_algorithms"] == ["kg_path"]
    assert report_bundle["main"]["num_negatives"] == 499
    assert report_bundle["legacy"]["num_negatives"] == 499
    assert prewarm_calls == []
    assert builder_calls == [
        {
            "user_source": "public",
            "num_negatives": 499,
            "negative_seeds": evaluator.NEGATIVE_SAMPLE_SEEDS,
        }
    ]


def test_save_results_keeps_history_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "BACKEND_DIR", str(tmp_path))
    report_bundle = {
        "main": {
            "protocol_version": 2,
            "generated_at": "2026-03-12T10:00:00+08:00",
            "eval_method": "main",
            "negative_sample_seeds": [42],
            "n_validation_users": 1,
            "n_test_users": 1,
            "results": {},
        },
        "legacy": {
            "protocol_version": 1,
            "generated_at": "2026-03-12T10:00:00+08:00",
            "eval_method": "legacy",
            "negative_sample_seeds": [42],
            "n_test_users": 1,
            "results": {},
        },
    }

    evaluator._save_results(report_bundle)

    reports_dir = tmp_path / "reports"
    history_dir = reports_dir / "history"
    assert (reports_dir / "eval_results.json").exists()
    assert (reports_dir / "eval_results_legacy.json").exists()
    assert (reports_dir / "eval_results.md").exists()
    assert (reports_dir / "eval_results_legacy.md").exists()

    history_json = sorted(path.name for path in history_dir.glob("*.json"))
    history_md = sorted(path.name for path in history_dir.glob("*.md"))
    assert history_json == [
        "2026-03-12_100000_eval_results.json",
        "2026-03-12_100000_eval_results_legacy.json",
    ]
    assert history_md == [
        "2026-03-12_100000_eval_results.md",
        "2026-03-12_100000_eval_results_legacy.md",
    ]

    with open(reports_dir / "eval_results.json", "r", encoding="utf-8") as file_obj:
        assert json.load(file_obj)["generated_at"] == "2026-03-12T10:00:00+08:00"


def test_save_results_uses_selected_algorithm_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "BACKEND_DIR", str(tmp_path))
    report_bundle = {
        "main": {
            "protocol_version": 2,
            "generated_at": "2026-03-12T10:00:00+08:00",
            "eval_method": "main",
            "negative_sample_seeds": [42],
            "selected_algorithms": ["kg_path"],
            "n_validation_users": 1,
            "n_test_users": 1,
            "results": {},
        },
        "legacy": {
            "protocol_version": 1,
            "generated_at": "2026-03-12T10:00:00+08:00",
            "eval_method": "legacy",
            "negative_sample_seeds": [42],
            "selected_algorithms": ["kg_path"],
            "n_test_users": 1,
            "results": {},
        },
    }

    evaluator._save_results(report_bundle)

    reports_dir = tmp_path / "reports"
    history_dir = reports_dir / "history"
    assert (reports_dir / "eval_results_kg_path.json").exists()
    assert (reports_dir / "eval_results_kg_path.md").exists()
    assert (reports_dir / "eval_results_kg_path_legacy.json").exists()
    assert (reports_dir / "eval_results_kg_path_legacy.md").exists()

    history_json = sorted(path.name for path in history_dir.glob("*.json"))
    assert history_json == [
        "2026-03-12_100000_eval_results_kg_path.json",
        "2026-03-12_100000_eval_results_kg_path_legacy.json",
    ]


def test_save_results_uses_negative_suffix_for_non_default_protocol(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "BACKEND_DIR", str(tmp_path))
    report_bundle = {
        "main": {
            "protocol_version": 2,
            "generated_at": "2026-03-12T10:00:00+08:00",
            "eval_method": "main",
            "negative_sample_seeds": [42],
            "num_negatives": 499,
            "n_validation_users": 1,
            "n_test_users": 1,
            "results": {},
        },
        "legacy": {
            "protocol_version": 1,
            "generated_at": "2026-03-12T10:00:00+08:00",
            "eval_method": "legacy",
            "negative_sample_seeds": [42],
            "num_negatives": 499,
            "n_test_users": 1,
            "results": {},
        },
    }

    evaluator._save_results(report_bundle)

    reports_dir = tmp_path / "reports"
    history_dir = reports_dir / "history"
    assert (reports_dir / "eval_results_neg499.json").exists()
    assert (reports_dir / "eval_results_neg499.md").exists()
    assert (reports_dir / "eval_results_neg499_legacy.json").exists()
    assert (reports_dir / "eval_results_neg499_legacy.md").exists()

    history_json = sorted(path.name for path in history_dir.glob("*.json"))
    assert history_json == [
        "2026-03-12_100000_eval_results_neg499.json",
        "2026-03-12_100000_eval_results_neg499_legacy.json",
    ]
