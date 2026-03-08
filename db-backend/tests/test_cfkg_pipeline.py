import json
import asyncio
from pathlib import Path
import random

from app.algorithms.cfkg.dataset import load_exported_dataset
from app.algorithms.cfkg.inference import (
    _collect_recall_candidates,
    _load_model_bundle,
    _rank_candidate_pool,
    _score_user_candidates,
)
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

    items = asyncio.run(
        _collect_recall_candidates(
            user_id=1,
            user_profile=None,
            seed_movie_ids=["m_seed"],
            seen_movie_ids=["m_seen"],
            limit=2,
            timeout_ms=800,
        )
    )

    assert [item["movie_id"] for item in items[:3]] == ["m1", "m2", "m3"]
    assert items[0]["source"] == "graph_cf"
    assert items[2]["source"] == "graph_content"


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
