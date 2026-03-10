import json
import asyncio
from pathlib import Path
import random
import math

from app.algorithms.cfkg.dataset import load_exported_dataset
from app.algorithms.cfkg.inference import (
    _combine_recall_support_scores,
    _collect_recall_candidates,
    _load_model_bundle,
    _rank_candidate_pool,
    _score_user_candidates,
    _MODEL_CACHE,
    prewarm_cfkg_model,
)
from app.algorithms.cfkg.reranker import (
    build_reranker_feature_map,
    load_reranker_bundle,
    save_reranker_artifact,
    score_reranker_features,
    train_reranker_model,
)
from app.algorithms.cfkg.reranker_training import _build_time_split_case
from app.algorithms.cfkg.training import (
    TrainingConfig,
    _sample_negative_movie,
    train_cfkg_model,
)
from app.services import recommend_service


def write_jsonl(path: Path, rows):
    with path.open("w", encoding="utf-8") as file_obj:
        for row in rows:
            file_obj.write(json.dumps(row, ensure_ascii=False))
            file_obj.write("\n")


def write_toy_cfkg_dataset(dataset_dir: Path):
    dataset_dir.mkdir(parents=True, exist_ok=True)
    entities = [
        {"entity_id": 0, "entity_key": "user:1", "entity_type": "User", "raw_id": "1", "label": "User 1"},
        {"entity_id": 1, "entity_key": "movie:m1", "entity_type": "Movie", "raw_id": "m1", "label": "Movie 1"},
        {"entity_id": 2, "entity_key": "movie:m2", "entity_type": "Movie", "raw_id": "m2", "label": "Movie 2"},
        {"entity_id": 3, "entity_key": "movie:m3", "entity_type": "Movie", "raw_id": "m3", "label": "Movie 3"},
        {"entity_id": 4, "entity_key": "genre:科幻", "entity_type": "Genre", "raw_id": "科幻", "label": "科幻"},
        {"entity_id": 5, "entity_key": "genre:喜剧", "entity_type": "Genre", "raw_id": "喜剧", "label": "喜剧"},
    ]
    relations = [
        {"relation_id": 0, "relation_name": "interact"},
        {"relation_id": 1, "relation_name": "rev_interact"},
        {"relation_id": 2, "relation_name": "has_genre"},
        {"relation_id": 3, "relation_name": "genre_of"},
        {"relation_id": 4, "relation_name": "directed_by"},
        {"relation_id": 5, "relation_name": "directs"},
        {"relation_id": 6, "relation_name": "acted_by"},
        {"relation_id": 7, "relation_name": "acts_in"},
    ]
    train_triples = [
        (0, 0, 1),
        (1, 1, 0),
        (1, 2, 4),
        (4, 3, 1),
        (2, 2, 4),
        (4, 3, 2),
        (3, 2, 5),
        (5, 3, 3),
    ]
    holdout_rows = [
        {
            "user_id": 1,
            "username": "user_1",
            "user_entity_id": 0,
            "train_positive_movie_ids": ["m1"],
            "train_positive_entity_ids": [1],
            "negative_movie_ids": ["m2"],
            "negative_entity_ids": [2],
            "seed_movie_ids": ["m1"],
            "seen_movie_ids": ["m1", "m2"],
            "holdout_movie_mid": "m3",
            "holdout_entity_id": 3,
            "split_time": "2026-03-08T12:00:00",
        }
    ]
    interaction_hard_negatives = [
        {
            "user_entity_id": 0,
            "positive_movie_entity_id": 1,
            "explicit_negative_entity_ids": [2],
            "semantic_negative_entity_ids": [3],
            "negative_entity_ids": [2, 3],
        }
    ]
    metadata = {
        "version": "toy",
        "entity_count": len(entities),
        "relation_count": len(relations),
        "train_triple_count": len(train_triples),
        "eval_triple_count": 1,
        "holdout_user_count": 1,
        "selected_user_count": 1,
        "movie_count": 3,
        "person_count": 0,
        "genre_count": 2,
        "interaction_negative_pool_count": len(interaction_hard_negatives),
        "relation_names": [
            "interact",
            "rev_interact",
            "has_genre",
            "genre_of",
            "directed_by",
            "directs",
            "acted_by",
            "acts_in",
        ],
    }

    write_jsonl(dataset_dir / "entities.jsonl", entities)
    write_jsonl(dataset_dir / "relations.jsonl", relations)
    with (dataset_dir / "triples_train.tsv").open("w", encoding="utf-8") as file_obj:
        for triple in train_triples:
            file_obj.write("\t".join(str(item) for item in triple) + "\n")
    with (dataset_dir / "triples_eval.tsv").open("w", encoding="utf-8") as file_obj:
        file_obj.write("0\t0\t3\n")
    write_jsonl(dataset_dir / "user_item_holdout.jsonl", holdout_rows)
    write_jsonl(dataset_dir / "interaction_hard_negatives.jsonl", interaction_hard_negatives)
    (dataset_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_load_exported_dataset_builds_stable_mappings(tmp_path):
    dataset_dir = tmp_path / "toy_dataset"
    write_toy_cfkg_dataset(dataset_dir)

    dataset = load_exported_dataset(dataset_dir)

    assert dataset.relation_name_to_id == {
        "interact": 0,
        "rev_interact": 1,
        "has_genre": 2,
        "genre_of": 3,
        "directed_by": 4,
        "directs": 5,
        "acted_by": 6,
        "acts_in": 7,
    }
    assert dataset.entity_key_to_id["user:1"] == 0
    assert dataset.movie_entity_ids == [1, 2, 3]
    assert dataset.movie_entity_id_to_mid[1] == "m1"
    assert dataset.user_positive_items[0] == {1}
    assert dataset.user_negative_items[0] == {2}
    assert dataset.interaction_explicit_negative_pools[(0, 1)] == [2]
    assert dataset.interaction_semantic_negative_pools[(0, 1)] == [3]
    assert dataset.interaction_hard_negative_pools[(0, 1)] == [2, 3]


def test_negative_sampler_uses_explicit_negative_movies(tmp_path):
    dataset_dir = tmp_path / "toy_dataset"
    write_toy_cfkg_dataset(dataset_dir)
    dataset = load_exported_dataset(dataset_dir)

    sampled = _sample_negative_movie(dataset, user_entity_id=0, excluded_movie_id=1, rng=random.Random(7))

    assert sampled == 2
    assert sampled not in dataset.user_positive_items[0]


def test_toy_training_ranks_positive_above_negative(tmp_path):
    dataset_dir = tmp_path / "toy_dataset"
    model_dir = tmp_path / "cfkg_model"
    write_toy_cfkg_dataset(dataset_dir)

    result = train_cfkg_model(
        TrainingConfig(
            dataset_dir=str(dataset_dir),
            output_dir=model_dir,
            embedding_dim=16,
            epochs=24,
            batch_size=2,
            learning_rate=5e-3,
            margin=1.0,
            hard_negative_weight=0.5,
            seed=17,
            device="cpu",
        )
    )
    bundle = _load_model_bundle(result["model_path"])
    torch = __import__("torch")

    user_entity_id = bundle["entity_key_to_id"]["user:1"]
    interact_relation_id = bundle["relation_name_to_id"]["interact"]
    positive_movie_id = bundle["entity_key_to_id"]["movie:m1"]
    negative_movie_id = bundle["entity_key_to_id"]["movie:m2"]

    with torch.no_grad():
        positive_score = bundle["model"].score(
            torch.tensor([user_entity_id]),
            torch.tensor([interact_relation_id]),
            torch.tensor([positive_movie_id]),
        ).item()
        negative_score = bundle["model"].score(
            torch.tensor([user_entity_id]),
            torch.tensor([interact_relation_id]),
            torch.tensor([negative_movie_id]),
        ).item()

    assert positive_score > negative_score


def test_score_user_candidates_respects_candidate_recall_pool(tmp_path):
    dataset_dir = tmp_path / "toy_dataset"
    model_dir = tmp_path / "cfkg_model"
    write_toy_cfkg_dataset(dataset_dir)

    result = train_cfkg_model(
        TrainingConfig(
            dataset_dir=str(dataset_dir),
            output_dir=model_dir,
            embedding_dim=16,
            epochs=12,
            batch_size=2,
            learning_rate=5e-3,
            margin=1.0,
            hard_negative_weight=0.5,
            seed=11,
            device="cpu",
        )
    )
    bundle = _load_model_bundle(result["model_path"])

    items = _score_user_candidates(
        bundle=bundle,
        user_id=1,
        seen_movie_ids=[],
        limit=5,
        candidate_movie_ids=["m3"],
    )

    assert [item["movie_id"] for item in items] == ["m3"]


def test_collect_recall_candidates_prefers_cf_and_uses_content_to_fill(monkeypatch):
    async def fake_cf_recall(**kwargs):
        return [
            {"movie_id": "m1", "score": 0.9, "recall_score": 0.9, "source": "graph_cf", "source_algorithms": ["graph_cf"]},
            {"movie_id": "m2", "score": 0.7, "recall_score": 0.7, "source": "graph_cf", "source_algorithms": ["graph_cf"]},
        ]

    async def fake_content_recall(**kwargs):
        return [
            {"movie_id": "m2", "score": 0.8, "recall_score": 0.8, "source": "graph_content", "source_algorithms": ["graph_content"]},
            {"movie_id": "m3", "score": 0.6, "recall_score": 0.6, "source": "graph_content", "source_algorithms": ["graph_content"]},
        ]

    monkeypatch.setattr("app.algorithms.cfkg.inference.get_graph_cf_recall_candidates", fake_cf_recall)
    monkeypatch.setattr("app.algorithms.cfkg.inference.get_graph_content_recall_candidates", fake_content_recall)
    stage_metrics = {}

    items = asyncio.run(
        _collect_recall_candidates(
            user_id=1,
            user_profile={
                "positive_features": {
                    "genres": {"科幻": 2.4, "悬疑": 1.7},
                    "directors": {},
                    "actors": {},
                }
            },
            seed_movie_ids=["m_seed"],
            seen_movie_ids=["m_seen"],
            limit=20,
            timeout_ms=800,
            stage_metrics=stage_metrics,
        )
    )

    assert [item["movie_id"] for item in items[:3]] == ["m1", "m2", "m3"]
    assert items[0]["source"] == "graph_cf"
    assert items[2]["source"] == "graph_content"
    assert stage_metrics["content_triggered"] is True
    assert stage_metrics["content_candidate_count"] == 2


def test_collect_recall_candidates_skips_content_when_cf_is_sufficient(monkeypatch):
    async def fake_cf_recall(**kwargs):
        return [
            {"movie_id": f"m{index}", "score": 1.0, "recall_score": 1.0, "source": "graph_cf", "source_algorithms": ["graph_cf"]}
            for index in range(45)
        ]

    async def fake_content_recall(**kwargs):
        raise AssertionError("content recall should not run when cf recall is already sufficient")

    monkeypatch.setattr("app.algorithms.cfkg.inference.get_graph_cf_recall_candidates", fake_cf_recall)
    monkeypatch.setattr("app.algorithms.cfkg.inference.get_graph_content_recall_candidates", fake_content_recall)
    stage_metrics = {}

    items = asyncio.run(
        _collect_recall_candidates(
            user_id=1,
            user_profile={
                "positive_features": {
                    "genres": {"科幻": 2.0, "悬疑": 1.0},
                    "directors": {},
                    "actors": {},
                }
            },
            seed_movie_ids=["m_seed"],
            seen_movie_ids=[],
            limit=20,
            timeout_ms=800,
            stage_metrics=stage_metrics,
        )
    )

    assert len(items) == 45
    assert stage_metrics["content_triggered"] is False
    assert stage_metrics["content_skip_reason"] == "cf_sufficient"


def test_collect_recall_candidates_skips_content_when_profile_signal_is_weak(monkeypatch):
    async def fake_cf_recall(**kwargs):
        return [
            {"movie_id": "m1", "score": 0.9, "recall_score": 0.9, "source": "graph_cf", "source_algorithms": ["graph_cf"]},
            {"movie_id": "m2", "score": 0.7, "recall_score": 0.7, "source": "graph_cf", "source_algorithms": ["graph_cf"]},
        ]

    async def fake_content_recall(**kwargs):
        raise AssertionError("content recall should not run when profile signal is weak")

    monkeypatch.setattr("app.algorithms.cfkg.inference.get_graph_cf_recall_candidates", fake_cf_recall)
    monkeypatch.setattr("app.algorithms.cfkg.inference.get_graph_content_recall_candidates", fake_content_recall)
    stage_metrics = {}

    items = asyncio.run(
        _collect_recall_candidates(
            user_id=1,
            user_profile={
                "positive_features": {
                    "genres": {"科幻": 2.0},
                    "directors": {},
                    "actors": {},
                }
            },
            seed_movie_ids=["m_seed"],
            seen_movie_ids=[],
            limit=20,
            timeout_ms=800,
            stage_metrics=stage_metrics,
        )
    )

    assert [item["movie_id"] for item in items] == ["m1", "m2"]
    assert stage_metrics["content_triggered"] is False
    assert stage_metrics["content_skip_reason"] == "weak_profile"


def test_collect_recall_candidates_merges_itemcf_when_conn_available(monkeypatch):
    async def fake_cf_recall(**kwargs):
        return [
            {"movie_id": "m1", "score": 0.9, "recall_score": 0.9, "source": "graph_cf", "source_algorithms": ["graph_cf"]},
            {"movie_id": "m2", "score": 0.7, "recall_score": 0.7, "source": "graph_cf", "source_algorithms": ["graph_cf"]},
        ]

    async def fake_itemcf(**kwargs):
        return [
            {"movie_id": "m2", "score": 0.8, "recall_score": 0.8, "source": "itemcf", "source_algorithms": ["itemcf"]},
            {"movie_id": "m3", "score": 0.6, "recall_score": 0.6, "source": "itemcf", "source_algorithms": ["itemcf"]},
        ]

    async def fake_content_recall(**kwargs):
        raise AssertionError("content recall should not run when profile signal is weak")

    monkeypatch.setattr("app.algorithms.cfkg.inference.get_graph_cf_recall_candidates", fake_cf_recall)
    monkeypatch.setattr("app.algorithms.cfkg.inference.get_itemcf_recommendations", fake_itemcf)
    monkeypatch.setattr("app.algorithms.cfkg.inference.get_graph_content_recall_candidates", fake_content_recall)
    stage_metrics = {}

    items = asyncio.run(
        _collect_recall_candidates(
            conn=object(),
            user_id=1,
            user_profile={
                "positive_features": {
                    "genres": {"科幻": 2.0},
                    "directors": {},
                    "actors": {},
                }
            },
            seed_movie_ids=["m_seed"],
            seen_movie_ids=[],
            limit=20,
            timeout_ms=800,
            stage_metrics=stage_metrics,
        )
    )

    assert [item["movie_id"] for item in items] == ["m1", "m2", "m3"]
    assert items[1]["source_algorithms"] == ["graph_cf", "itemcf"]
    assert stage_metrics["itemcf_candidate_count"] == 2
    assert stage_metrics["content_skip_reason"] == "weak_profile"


def test_combine_recall_support_scores_rewards_multi_source_support():
    combined = _combine_recall_support_scores([0.7, 0.6])

    assert combined > 0.7
    assert combined < 1.0
    assert _combine_recall_support_scores([0.0, 0.0]) == 0.0


def test_reranker_feature_map_marks_itemcf_source():
    feature_map = build_reranker_feature_map(
        recall_score=0.8,
        cfkg_score=0.6,
        profile_score=0.2,
        recall_sources=["graph_cf", "itemcf"],
        negative_signals=[],
    )

    assert feature_map["has_cf_source"] == 1.0
    assert feature_map["has_itemcf_source"] == 1.0
    assert feature_map["source_count"] == 2.0


def test_reranker_training_time_split_case_includes_pref_history(monkeypatch):
    monkeypatch.setattr(
        "app.algorithms.cfkg.reranker_training.fetch_movie_graph_profile_map",
        lambda driver, movie_ids, timeout_ms=None: {},
    )
    monkeypatch.setattr(
        "app.algorithms.cfkg.reranker_training.Neo4jConnection.get_driver",
        lambda: object(),
    )

    case = _build_time_split_case(
        rating_rows=[
            {"id": 1, "user_id": 9, "mid": "m1", "rating": 4.5, "rated_at": "2025-01-01T10:00:00", "updated_at": "2025-01-01T10:00:00"},
            {"id": 2, "user_id": 9, "mid": "m2", "rating": 2.0, "rated_at": "2025-01-02T10:00:00", "updated_at": "2025-01-02T10:00:00"},
            {"id": 3, "user_id": 9, "mid": "m4", "rating": 4.0, "rated_at": "2025-01-04T10:00:00", "updated_at": "2025-01-04T10:00:00"},
        ],
        pref_rows=[
            {"id": 1, "user_id": 9, "mid": "m3", "pref_type": "want_to_watch", "created_at": "2025-01-03T10:00:00", "updated_at": "2025-01-03T10:00:00"},
        ],
    )

    assert case is not None
    assert case["holdout_movie_id"] == "m4"
    assert "m1" in case["seed_movie_ids"]
    assert "m3" in case["user_profile"]["movie_feedback"]


def test_collect_recall_candidates_skips_content_when_gap_is_small(monkeypatch):
    async def fake_cf_recall(**kwargs):
        return [
            {"movie_id": f"m{index}", "score": 1.0, "recall_score": 1.0, "source": "graph_cf", "source_algorithms": ["graph_cf"]}
            for index in range(30)
        ]

    async def fake_content_recall(**kwargs):
        raise AssertionError("content recall should not run when the gap is below the threshold")

    monkeypatch.setattr("app.algorithms.cfkg.inference.get_graph_cf_recall_candidates", fake_cf_recall)
    monkeypatch.setattr("app.algorithms.cfkg.inference.get_graph_content_recall_candidates", fake_content_recall)
    stage_metrics = {}

    items = asyncio.run(
        _collect_recall_candidates(
            user_id=1,
            user_profile={
                "positive_features": {
                    "genres": {"科幻": 2.4, "悬疑": 1.7},
                    "directors": {},
                    "actors": {},
                }
            },
            seed_movie_ids=["m_seed"],
            seen_movie_ids=[],
            limit=16,
            timeout_ms=800,
            stage_metrics=stage_metrics,
        )
    )

    assert len(items) == 30
    assert stage_metrics["content_triggered"] is False
    assert stage_metrics["content_skip_reason"] == "small_gap"


def test_collect_recall_candidates_timeout_keeps_cf_candidates(monkeypatch):
    async def fake_cf_recall(**kwargs):
        return [
            {"movie_id": "m1", "score": 0.9, "recall_score": 0.9, "source": "graph_cf", "source_algorithms": ["graph_cf"]},
            {"movie_id": "m2", "score": 0.7, "recall_score": 0.7, "source": "graph_cf", "source_algorithms": ["graph_cf"]},
        ]

    async def fake_content_recall(**kwargs):
        raise asyncio.TimeoutError()

    monkeypatch.setattr("app.algorithms.cfkg.inference.get_graph_cf_recall_candidates", fake_cf_recall)
    monkeypatch.setattr("app.algorithms.cfkg.inference.get_graph_content_recall_candidates", fake_content_recall)
    stage_metrics = {}

    items = asyncio.run(
        _collect_recall_candidates(
            user_id=1,
            user_profile={
                "positive_features": {
                    "genres": {"科幻": 2.4, "悬疑": 1.7},
                    "directors": {},
                    "actors": {},
                }
            },
            seed_movie_ids=["m_seed"],
            seen_movie_ids=[],
            limit=20,
            timeout_ms=800,
            stage_metrics=stage_metrics,
        )
    )

    assert [item["movie_id"] for item in items] == ["m1", "m2"]
    assert stage_metrics["content_triggered"] is True
    assert stage_metrics["content_timed_out"] is True
    assert stage_metrics["content_skip_reason"] == "timeout"


def test_content_query_uses_legacy_compatible_subquery_syntax():
    from app.algorithms import graph_content

    assert "CALL {" in graph_content.CONTENT_QUERY
    assert "CALL (" not in graph_content.CONTENT_QUERY


def test_prewarm_cfkg_model_populates_bundle_cache(tmp_path):
    dataset_dir = tmp_path / "toy_dataset"
    model_dir = tmp_path / "cfkg_model"
    write_toy_cfkg_dataset(dataset_dir)

    result = train_cfkg_model(
        TrainingConfig(
            dataset_dir=str(dataset_dir),
            output_dir=model_dir,
            embedding_dim=16,
            epochs=8,
            batch_size=2,
            learning_rate=5e-3,
            margin=1.0,
            hard_negative_weight=0.5,
            seed=23,
            device="cpu",
        )
    )

    warmed = asyncio.run(prewarm_cfkg_model(result["model_path"]))

    assert warmed is True
    assert _MODEL_CACHE["bundle"] is not None
    assert _MODEL_CACHE["path"] == str(result["model_path"])


def test_prewarm_cfkg_model_handles_missing_model():
    warmed = asyncio.run(prewarm_cfkg_model("output/models/cfkg/does-not-exist.pt"))

    assert warmed is False


def test_rank_candidate_pool_combines_recall_cfkg_and_profile(monkeypatch):
    bundle = {
        "entity_key_to_id": {"user:1": 0},
        "relation_name_to_id": {"interact": 0},
        "movie_entity_ids": [1, 2],
        "movie_entity_id_to_mid": {1: "m1", 2: "m2"},
        "entity_id_to_label": {1: "Movie 1", 2: "Movie 2"},
        "model": object(),
    }
    candidate_items = [
        {
            "movie_id": "m1",
            "title": "Movie 1",
            "recall_score": 0.2,
            "source": "graph_cf",
            "source_algorithms": ["graph_cf"],
            "reasons": ["cf recall"],
        },
        {
            "movie_id": "m2",
            "title": "Movie 2",
            "recall_score": 1.0,
            "source": "graph_content",
            "source_algorithms": ["graph_content"],
            "reasons": ["content recall"],
        },
    ]

    monkeypatch.setattr(
        "app.algorithms.cfkg.inference._score_user_candidates",
        lambda **kwargs: [
            {"movie_id": "m1", "title": "Movie 1", "score": 0.9},
            {"movie_id": "m2", "title": "Movie 2", "score": 0.2},
        ],
    )
    monkeypatch.setattr(
        "app.algorithms.cfkg.inference.fetch_movie_graph_profile_map",
        lambda driver, movie_ids, timeout_ms=None: {movie_id: {"genres": {"科幻"}} for movie_id in movie_ids},
    )
    monkeypatch.setattr(
        "app.algorithms.cfkg.inference.score_movie_against_user_profile",
        lambda movie_profile, user_profile: (0.6 if movie_profile else 0.0, ["profile"], []),
    )
    monkeypatch.setattr(
        "app.algorithms.cfkg.inference.Neo4jConnection.get_driver",
        lambda: object(),
    )
    monkeypatch.setattr(
        "app.algorithms.cfkg.inference.load_reranker_bundle",
        lambda: None,
    )

    ranked = _rank_candidate_pool(
        bundle=bundle,
        user_id=1,
        candidate_items=candidate_items,
        seen_movie_ids=[],
        user_profile={"positive_features": {"genres": {"科幻": 1.0}}},
        seed_movie_ids=["m_seed"],
        timeout_ms=800,
        ranking_mode="pipeline",
        limit=5,
    )

    assert [item["movie_id"] for item in ranked] == ["m2", "m1"]
    assert ranked[0]["score_breakdown"]["graph_content"] == 0.5
    assert ranked[0]["score_breakdown"]["cfkg"] == 0.0
    assert ranked[0]["score_breakdown"]["profile"] == 0.09
    assert ranked[1]["score_breakdown"]["graph_cf"] == 0.0
    assert ranked[1]["score_breakdown"]["cfkg"] == 0.35


def test_reranker_artifact_round_trip_scores_positive_higher(tmp_path):
    positive_feature = build_reranker_feature_map(
        recall_score=0.8,
        cfkg_score=0.9,
        profile_score=0.6,
        recall_sources=["graph_cf", "graph_content"],
        negative_signals=[],
    )
    negative_feature = build_reranker_feature_map(
        recall_score=0.1,
        cfkg_score=0.2,
        profile_score=0.0,
        recall_sources=["graph_content"],
        negative_signals=["skip_actor"],
    )
    feature_rows = [positive_feature, negative_feature, positive_feature, negative_feature]
    labels = [1, 0, 1, 0]

    artifact = train_reranker_model(
        feature_rows,
        labels,
        iterations=300,
        learning_rate=0.1,
        l2=0.001,
    )
    output_path = tmp_path / "reranker.json"
    saved_path = save_reranker_artifact(artifact, output_path)
    bundle = load_reranker_bundle(saved_path)

    positive_score, positive_contrib = score_reranker_features(bundle, positive_feature)
    negative_score, negative_contrib = score_reranker_features(bundle, negative_feature)

    assert Path(saved_path).exists()
    assert bundle["metrics"]["training_row_count"] == 4
    assert positive_score > negative_score
    assert math.isfinite(positive_contrib["cfkg_score"])
    assert math.isfinite(negative_contrib["negative_signal_count"])


def test_reranker_scoring_supports_older_feature_sets(tmp_path):
    artifact = {
        "feature_names": ["recall_score", "cfkg_score", "profile_score"],
        "weights": [1.2, 0.8, 0.4],
        "bias": -0.2,
        "means": [0.0, 0.0, 0.0],
        "scales": [1.0, 1.0, 1.0],
        "metrics": {"training_row_count": 1},
    }
    output_path = tmp_path / "legacy-reranker.json"
    saved_path = save_reranker_artifact(artifact, output_path)
    bundle = load_reranker_bundle(saved_path)

    score, contribution_map = score_reranker_features(
        bundle,
        build_reranker_feature_map(
            recall_score=0.7,
            cfkg_score=0.8,
            profile_score=0.6,
            recall_sources=["graph_cf"],
            negative_signals=[],
        ),
    )

    assert score > 0.5
    assert set(contribution_map) == {"recall_score", "cfkg_score", "profile_score"}


def test_rank_candidate_pool_uses_learned_reranker_when_available(monkeypatch):
    bundle = {
        "entity_key_to_id": {"user:1": 0},
        "relation_name_to_id": {"interact": 0},
        "movie_entity_ids": [1, 2],
        "movie_entity_id_to_mid": {1: "m1", 2: "m2"},
        "entity_id_to_label": {1: "Movie 1", 2: "Movie 2"},
        "model": object(),
    }
    candidate_items = [
        {
            "movie_id": "m1",
            "title": "Movie 1",
            "recall_score": 0.1,
            "source": "graph_cf",
            "source_algorithms": ["graph_cf"],
            "reasons": ["cf recall"],
        },
        {
            "movie_id": "m2",
            "title": "Movie 2",
            "recall_score": 1.0,
            "source": "graph_content",
            "source_algorithms": ["graph_content"],
            "reasons": ["content recall"],
        },
    ]

    monkeypatch.setattr(
        "app.algorithms.cfkg.inference._score_user_candidates",
        lambda **kwargs: [
            {"movie_id": "m1", "title": "Movie 1", "score": 0.9},
            {"movie_id": "m2", "title": "Movie 2", "score": 0.1},
        ],
    )
    monkeypatch.setattr(
        "app.algorithms.cfkg.inference.fetch_movie_graph_profile_map",
        lambda driver, movie_ids, timeout_ms=None: {},
    )
    monkeypatch.setattr(
        "app.algorithms.cfkg.inference.score_movie_against_user_profile",
        lambda movie_profile, user_profile: (0.0, [], []),
    )
    monkeypatch.setattr(
        "app.algorithms.cfkg.inference.Neo4jConnection.get_driver",
        lambda: object(),
    )
    monkeypatch.setattr(
        "app.algorithms.cfkg.inference.load_reranker_bundle",
        lambda: {"path": "memory://reranker"},
    )
    monkeypatch.setattr(
        "app.algorithms.cfkg.inference.score_reranker_features",
        lambda bundle, feature_map: (
            feature_map["cfkg_score"],
            {
                "recall_score": 0.0,
                "cfkg_score": feature_map["cfkg_score"],
                "profile_score": 0.0,
                "source_count": 0.0,
                "has_cf_source": 0.0,
                "has_content_source": 0.0,
                "has_ppr_source": 0.0,
                "negative_signal_count": 0.0,
            },
        ),
    )

    ranked = _rank_candidate_pool(
        bundle=bundle,
        user_id=1,
        candidate_items=candidate_items,
        seen_movie_ids=[],
        user_profile={"positive_features": {"genres": {"科幻": 1.0}}},
        seed_movie_ids=["m_seed"],
        timeout_ms=800,
        ranking_mode="pipeline",
        limit=5,
    )

    assert [item["movie_id"] for item in ranked] == ["m1", "m2"]
    assert ranked[0]["score_breakdown"]["cfkg"] == 1.0
    assert "profile" not in ranked[0]["score_breakdown"]


def test_cfkg_explain_payload_adds_meta_path_template(monkeypatch):
    monkeypatch.setattr(
        recommend_service,
        "_build_user_profile",
        lambda conn, user_id: {
            "representative_movie_ids": ["m1"],
            "profile_highlights": [{"type": "genre", "label": "科幻"}],
            "summary": {"cold_start": False},
        },
    )
    monkeypatch.setattr(
        recommend_service,
        "_fetch_movie_brief_map",
        lambda movie_ids, timeout_ms=None: {
            "m1": {"mid": "m1", "title": "Movie 1", "rating": 8.0, "year": 2024, "cover": None},
            "m2": {"mid": "m2", "title": "Movie 2", "rating": 8.3, "year": 2025, "cover": None},
        },
    )
    monkeypatch.setattr(
        recommend_service,
        "fetch_movie_graph_profile_map",
        lambda driver, movie_ids, timeout_ms=None: {"m2": {"genres": {"科幻"}}},
    )
    monkeypatch.setattr(
        recommend_service,
        "score_movie_against_user_profile",
        lambda movie_profile, user_profile: (0.4, ["命中偏好类型 科幻"], []),
    )
    monkeypatch.setattr(
        recommend_service,
        "run_query",
        lambda session, query, timeout_ms=None, **params: [
            {
                "representative_mid": "m1",
                "rel_type": "HAS_GENRE",
                "shared_type": "Genre",
                "shared_mid": None,
                "shared_pid": None,
                "shared_label": "科幻",
                "shared_rating": None,
                "shared_year": None,
            }
        ],
    )

    class DummySession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummyDriver:
        def session(self):
            return DummySession()

    monkeypatch.setattr(recommend_service.Neo4jConnection, "get_driver", lambda: DummyDriver())

    payload = recommend_service.build_recommendation_explain_payload(
        conn=object(),
        user_id=1,
        target_mid="m2",
        algorithm="cfkg",
    )

    assert payload["algorithm"] == "cfkg"
    assert payload["reason_paths"][0]["template"] == "User -> Movie -> Genre -> Movie"
    assert payload["meta"]["has_graph_evidence"] is True


def test_cfkg_explain_payload_falls_back_to_signal_node(monkeypatch):
    monkeypatch.setattr(
        recommend_service,
        "_build_user_profile",
        lambda conn, user_id: {
            "representative_movie_ids": ["m1"],
            "profile_highlights": [{"type": "genre", "label": "科幻"}],
            "summary": {"cold_start": False},
        },
    )
    monkeypatch.setattr(
        recommend_service,
        "_fetch_movie_brief_map",
        lambda movie_ids, timeout_ms=None: {
            "m1": {"mid": "m1", "title": "Movie 1", "rating": 8.0, "year": 2024, "cover": None},
            "m2": {"mid": "m2", "title": "Movie 2", "rating": 8.3, "year": 2025, "cover": None},
        },
    )
    monkeypatch.setattr(
        recommend_service,
        "fetch_movie_graph_profile_map",
        lambda driver, movie_ids, timeout_ms=None: {"m2": {"genres": {"科幻"}}},
    )
    monkeypatch.setattr(
        recommend_service,
        "score_movie_against_user_profile",
        lambda movie_profile, user_profile: (0.4, ["命中偏好类型 科幻"], []),
    )
    monkeypatch.setattr(recommend_service, "run_query", lambda session, query, timeout_ms=None, **params: [])

    class DummySession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummyDriver:
        def session(self):
            return DummySession()

    monkeypatch.setattr(recommend_service.Neo4jConnection, "get_driver", lambda: DummyDriver())

    payload = recommend_service.build_recommendation_explain_payload(
        conn=object(),
        user_id=1,
        target_mid="m2",
        algorithm="cfkg",
    )

    assert payload["meta"]["has_graph_evidence"] is False
    assert any(edge["type"] == "CFKG_SIGNAL" for edge in payload["edges"])


def test_fallback_recommendations_use_mysql_when_neo4j_times_out(monkeypatch):
    monkeypatch.setattr(
        recommend_service,
        "run_query",
        lambda session, query, timeout_ms=None, **params: (_ for _ in ()).throw(RuntimeError("neo4j timeout")),
    )

    class DummySession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummyDriver:
        def session(self):
            return DummySession()

    class DummyCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params):
            self.query = query
            self.params = params

        def fetchall(self):
            return [
                {
                    "movie_id": "m2",
                    "title": "Movie 2",
                    "rating": 8.8,
                    "votes": 100000,
                    "hybrid_score": 8.3,
                }
            ]

    class DummyConn:
        def cursor(self):
            return DummyCursor()

    monkeypatch.setattr(recommend_service.Neo4jConnection, "get_driver", lambda: DummyDriver())

    items = recommend_service._get_fallback_recommendations(
        algorithm="cfkg",
        seen_movie_ids=["m1"],
        limit=5,
        conn=DummyConn(),
    )

    assert items[0]["movie_id"] == "m2"
    assert items[0]["score"] == 8.3
    assert items[0]["source"] == "cfkg"


def test_movie_brief_map_uses_mysql_when_neo4j_times_out(monkeypatch):
    monkeypatch.setattr(
        recommend_service,
        "run_query",
        lambda session, query, timeout_ms=None, **params: (_ for _ in ()).throw(RuntimeError("neo4j timeout")),
    )

    class DummyCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params):
            self.query = query
            self.params = params

        def fetchall(self):
            return [
                {
                    "mid": "m2",
                    "title": "Movie 2",
                    "rating": 8.7,
                    "year": 2024,
                    "cover": "cover.jpg",
                    "genres": "科幻/动作",
                }
            ]

    class DummyConn:
        def cursor(self):
            return DummyCursor()

    brief_map = recommend_service._fetch_movie_brief_map_safe(
        conn=DummyConn(),
        movie_ids=["m2"],
        timeout_ms=500,
    )

    assert brief_map["m2"]["title"] == "Movie 2"
    assert brief_map["m2"]["cover"] == "cover.jpg"
    assert brief_map["m2"]["genres"] == ["科幻", "动作"]
