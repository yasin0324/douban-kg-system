import numpy as np
import pytest
from unittest.mock import patch

from app.algorithms.cfkg import CFKGRecommender
from app.algorithms.graph_cache import (
    GraphMetadataCache,
    MovieGraphProfile,
    REL_ACTOR,
    REL_DIRECTOR,
)
from app.algorithms.item_cf import ItemCFRecommender
from app.algorithms.kg_embed import KGEmbedRecommender
from app.algorithms.kg_path import KGPathRecommender


def setup_function():
    GraphMetadataCache.clear()
    KGEmbedRecommender.clear_shared_artifacts()


def teardown_function():
    GraphMetadataCache.clear()
    KGEmbedRecommender.clear_shared_artifacts()


def test_graph_cache_build_triples_excludes_user_and_rated_relations():
    GraphMetadataCache._loaded = True
    GraphMetadataCache._movie_profiles = {
        "m1": MovieGraphProfile(
            mid="m1",
            name="Movie 1",
            content_type="movie",
            year=2012,
            year_bucket="2010s",
            genres={"剧情"},
            regions={"中国"},
            languages={"汉语"},
            directors={"p1"},
            actors={"p2", "p3"},
            top_actors={"p2"},
        )
    }
    GraphMetadataCache._movie_mids = ["m1"]
    GraphMetadataCache._movie_name_map = {"m1": "Movie 1"}
    GraphMetadataCache._triples_cache = {}

    recommender = KGEmbedRecommender(use_expanded_relations=True)
    triples, movie_mids, entity_types, relation_types = recommender._export_triples()

    assert movie_mids == {"m1"}
    assert triples
    assert all("user_" not in head and "user_" not in tail for head, _, tail in triples)
    assert all(rel != "RATED" and not rel.endswith("RATED_REV") for _, rel, _ in triples)
    assert "region_中国" in entity_types
    assert "language_汉语" in entity_types
    assert "content_type_movie" in entity_types
    assert "year_bucket_2010s" in entity_types
    assert "IN_REGION" in relation_types
    assert "IN_LANGUAGE" in relation_types
    assert "HAS_CONTENT_TYPE" in relation_types
    assert "IN_YEAR_BUCKET" in relation_types


def test_kg_embed_negative_sampling_respects_entity_types():
    recommender = KGEmbedRecommender()
    batch = np.array(
        [
            [10, 0, 20],  # person -> movie
            [30, 1, 40],  # movie -> genre
        ],
        dtype=np.int32,
    )
    relation_idx_to_types = {
        0: ("person", "movie"),
        1: ("movie", "genre"),
    }
    type_to_entity_indices = {
        "person": np.array([10, 11, 12], dtype=np.int32),
        "movie": np.array([20, 21, 22, 30, 31], dtype=np.int32),
        "genre": np.array([40, 41, 42], dtype=np.int32),
    }

    negatives = recommender._sample_negative_batch(
        batch=batch,
        relation_idx_to_types=relation_idx_to_types,
        type_to_entity_indices=type_to_entity_indices,
        rng=np.random.default_rng(7),
    )

    assert negatives.shape == batch.shape
    assert negatives[0, 0] in type_to_entity_indices["person"]
    assert negatives[0, 2] in type_to_entity_indices["movie"]
    assert negatives[1, 0] in type_to_entity_indices["movie"]
    assert negatives[1, 2] in type_to_entity_indices["genre"]


def test_kg_embed_skips_online_training_when_disabled_and_files_missing():
    recommender = KGEmbedRecommender()

    with (
        patch("app.algorithms.kg_embed.os.path.exists", return_value=False),
        patch("app.algorithms.kg_embed.settings.RECOMMEND_ENABLE_ONLINE_EMBED_TRAINING", False),
        patch.object(recommender, "_train_transe") as mock_train,
    ):
        artifacts = recommender._load_or_train()

    assert artifacts is None
    mock_train.assert_not_called()


def test_kg_embed_overlap_reason_uses_person_names():
    GraphMetadataCache._loaded = True
    GraphMetadataCache._person_name_map = {
        "p1": "克里斯托弗·诺兰 Christopher Nolan",
        "p2": "莱昂纳多·迪卡普里奥 Leonardo DiCaprio",
    }

    recommender = KGEmbedRecommender()

    assert recommender._overlap_reason(REL_DIRECTOR, "p1") == (
        "偏好相同导演 克里斯托弗·诺兰 Christopher Nolan"
    )
    assert recommender._overlap_reason(REL_ACTOR, "p2") == (
        "偏好相同演员 莱昂纳多·迪卡普里奥 Leonardo DiCaprio"
    )


def test_kg_path_scoring_matches_manual_accumulation():
    recommender = KGPathRecommender(
        director_weight=1.0,
        actor_weight=0.6,
        genre_weight=0.4,
        two_hop_weight=0.2,
        enable_two_hop=True,
        use_degree_penalty=False,
    )
    evidence = {
        "candidate_evidence": {
            "m1": [
                {
                    "relation": "director",
                    "entity_ids": ["p1"],
                    "entity_names": ["导演A"],
                    "strength": 0.8,
                    "hits": 1,
                },
                {
                    "relation": "actor",
                    "entity_ids": ["p2"],
                    "entity_names": ["演员B"],
                    "strength": 0.5,
                    "hits": 1,
                },
            ],
            "m2": [
                {
                    "relation": "genre",
                    "entity_ids": ["剧情", "悬疑"],
                    "entity_names": ["剧情", "悬疑"],
                    "strength": 0.9,
                    "hits": 2,
                },
                {
                    "relation": "actor_actor",
                    "entity_ids": ["p3"],
                    "entity_names": ["演员C"],
                    "strength": 0.4,
                    "hits": 1,
                },
            ],
        }
    }

    scored = recommender._score_candidates(evidence)

    assert set(scored["candidate_scores"]) == {"m1", "m2"}
    assert scored["candidate_paths"]["m1"] == 2
    assert scored["candidate_paths"]["m2"] == 3
    assert scored["candidate_scores"]["m1"] == pytest.approx(0.8 + (0.5 * 0.6))
    assert scored["candidate_scores"]["m2"] == pytest.approx((0.9 * 0.4) + (0.4 * 0.2))
    assert len(scored["candidate_reasons"]["m1"]) <= 3
    assert len(scored["candidate_reasons"]["m2"]) <= 3


def test_movie_graph_profile_ordered_actor_ids_respects_order_and_pid_tie_break():
    profile = MovieGraphProfile(
        mid="m1",
        name="Movie 1",
        actors={"p9", "p3", "p2", "p1"},
        actor_orders={"p3": 2, "p2": 2, "p1": 1},
    )

    assert profile.ordered_actor_ids() == ["p1", "p2", "p3", "p9"]
    assert profile.ordered_actor_ids(2) == ["p1", "p2", "p3"]


def test_kg_path_actor_order_limit_filters_candidates():
    recommender = KGPathRecommender()
    GraphMetadataCache._loaded = True
    GraphMetadataCache._person_name_map = {"p1": "演员A"}
    keep_profile = MovieGraphProfile(
        mid="keep",
        name="Keep",
        actors={"p1"},
        top_actors={"p1"},
        actor_orders={"p1": 3},
    )
    drop_profile = MovieGraphProfile(
        mid="drop",
        name="Drop",
        actors={"p1"},
        top_actors={"p1"},
        actor_orders={"p1": 5},
    )

    records = recommender._build_one_hop_records(
        relation="actor",
        seed_mid="seed",
        seed_weight=1.0,
        seed_entity_ids={"p1"},
        inverted_index={"p1": {"seed", "keep", "drop"}},
        per_seed_limit=10,
        candidate_profiles={"keep": keep_profile, "drop": drop_profile},
        actor_order_limit=3,
    )

    assert [record["mid"] for record in records] == ["keep"]


def test_kg_path_one_hop_shared_actor_ids_follow_candidate_actor_order():
    recommender = KGPathRecommender()
    GraphMetadataCache._loaded = True
    GraphMetadataCache._person_name_map = {"p1": "演员A", "p9": "演员B"}
    candidate_profile = MovieGraphProfile(
        mid="cand",
        name="Candidate",
        actors={"p1", "p9"},
        top_actors={"p1", "p9"},
        actor_orders={"p9": 1, "p1": 3},
    )

    records = recommender._build_one_hop_records(
        relation="actor",
        seed_mid="seed",
        seed_weight=1.0,
        seed_entity_ids=["p1", "p9"],
        inverted_index={"p1": {"seed", "cand"}, "p9": {"seed", "cand"}},
        per_seed_limit=10,
        candidate_profiles={"cand": candidate_profile},
        actor_order_limit=5,
    )

    assert [record["mid"] for record in records] == ["cand"]
    assert records[0]["entity_ids"] == ["p9", "p1"]
    assert records[0]["entity_names"] == ["演员B", "演员A"]


def test_kg_path_two_hop_shared_actor_ids_follow_candidate_actor_order():
    recommender = KGPathRecommender()
    GraphMetadataCache._loaded = True
    GraphMetadataCache._person_name_map = {"p1": "演员A", "p2": "演员B", "p3": "演员C"}
    seed_profile = MovieGraphProfile(
        mid="seed",
        name="Seed",
        actors={"p1"},
        top_actors={"p1"},
        actor_orders={"p1": 1},
    )
    bridge_profile = MovieGraphProfile(
        mid="bridge",
        name="Bridge",
        actors={"p1", "p2", "p3"},
        top_actors={"p1", "p2", "p3"},
        actor_orders={"p1": 1, "p2": 2, "p3": 5},
    )
    candidate_profile = MovieGraphProfile(
        mid="cand",
        name="Candidate",
        actors={"p2", "p3"},
        top_actors={"p2", "p3"},
        actor_orders={"p3": 1, "p2": 4},
    )

    records = recommender._build_two_hop_records(
        seed_mid="seed",
        seed_profile=seed_profile,
        seed_weight=1.0,
        actor_index={
            "p1": {"seed", "bridge"},
            "p2": {"bridge", "cand"},
            "p3": {"bridge", "cand"},
        },
        profiles={"seed": seed_profile, "bridge": bridge_profile, "cand": candidate_profile},
        per_seed_limit=10,
        actor_order_limit=5,
    )

    assert [record["mid"] for record in records] == ["cand"]
    assert records[0]["entity_ids"] == ["p3", "p2"]
    assert records[0]["entity_names"] == ["演员C", "演员B"]


def test_kg_path_select_genres_prefers_rare_entities():
    GraphMetadataCache._loaded = True
    GraphMetadataCache._relation_degrees = {
        "genre": {
            "剧情": 50000,
            "悬疑": 4000,
            "犯罪": 6000,
        }
    }
    recommender = KGPathRecommender(genre_seed_entity_limit=2, genre_max_degree=15000)

    selected = recommender._select_genres({"剧情", "悬疑", "犯罪"})

    assert selected == {"悬疑", "犯罪"}


class StubRecommender:
    def __init__(self, rows):
        self.rows = list(rows)

    def recommend(self, user_id, n=20, exclude_mids=None, exclude_from_training=None):
        return self.rows[:n]


class _FakeCursor:
    def __init__(self, fetchall_results):
        self.fetchall_results = list(fetchall_results)

    def execute(self, sql, params=None):
        return None

    def fetchall(self):
        if self.fetchall_results:
            return self.fetchall_results.pop(0)
        return []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self, fetchall_results):
        self._cursor = _FakeCursor(fetchall_results)

    def cursor(self):
        return self._cursor


def test_cfkg_merges_candidates_and_prioritizes_kg_reasons():
    recommender = CFKGRecommender()
    recommender._item_cf = StubRecommender(
        [
            {"mid": "m1", "score": 0.9, "reason": "item_cf reason"},
            {"mid": "m2", "score": 0.8, "reason": "item_cf reason 2"},
        ]
    )
    recommender._kg_embed = StubRecommender(
        [
            {"mid": "m1", "score": 0.7, "reason": "kg_embed reason"},
            {"mid": "m3", "score": 0.6, "reason": "kg_embed reason 2"},
        ]
    )
    recommender._kg_path = StubRecommender(
        [
            {"mid": "m1", "score": 0.5, "reason": "kg_path reason"},
            {"mid": "m4", "score": 0.9, "reason": "kg_path reason 2"},
        ]
    )
    recommender._content = StubRecommender([])

    results = recommender.recommend(user_id=1, n=10)

    assert [row["mid"] for row in results] == ["m1", "m2", "m3", "m4"]
    assert results[0]["source_algorithms"] == ["item_cf", "kg_embed", "kg_path"]
    assert results[0]["reasons"] == ["kg_path reason", "kg_embed reason", "item_cf reason"]
    assert results[0]["reason"] == "kg_path reason"


def test_cfkg_resolve_branch_weights_renormalizes_when_item_cf_missing():
    recommender = CFKGRecommender()

    weights = recommender._resolve_branch_weights(
        {
            "item_cf": [],
            "kg_embed": [{"mid": "m1", "score": 1.0, "reason": "kg"}],
            "kg_path": [{"mid": "m2", "score": 1.0, "reason": "path"}],
        }
    )

    assert "item_cf" not in weights
    assert weights["kg_embed"] == pytest.approx(0.75)
    assert weights["kg_path"] == pytest.approx(0.25)


def test_cfkg_uses_content_as_fallback_candidates():
    recommender = CFKGRecommender()
    recommender._item_cf = StubRecommender([])
    recommender._kg_embed = StubRecommender(
        [{"mid": "m1", "score": 1.0, "reason": "kg_embed reason"}]
    )
    recommender._kg_path = StubRecommender([])
    recommender._content = StubRecommender(
        [{"mid": "m2", "score": 0.9, "reason": "content reason"}]
    )

    results = recommender.recommend(user_id=1, n=5)

    assert [row["mid"] for row in results] == ["m1", "m2"]
    assert results[0]["source_algorithms"] == ["kg_embed"]
    assert results[1]["source_algorithms"] == ["content"]
    assert results[1]["reason"] == "content reason"


def test_kg_embed_caps_positive_signals_for_heavy_users():
    recommender = KGEmbedRecommender(
        max_positive_rating_seeds=2,
        max_like_seeds=1,
        max_wish_seeds=0,
    )
    conn = _FakeConn(
        [
            [
                {"mid": "r1", "rating": 5.0, "rated_at": "2026-03-10 10:00:00"},
                {"mid": "r2", "rating": 4.5, "rated_at": "2026-03-09 10:00:00"},
                {"mid": "r3", "rating": 4.0, "rated_at": "2026-03-08 10:00:00"},
            ],
            [
                {"mid": "l1", "pref_type": "like", "created_at": "2026-03-10 12:00:00"},
                {"mid": "w1", "pref_type": "want_to_watch", "created_at": "2026-03-10 13:00:00"},
            ],
        ]
    )

    result = recommender.get_user_positive_movies(conn, user_id=1)

    assert [row["mid"] for row in result] == ["r1", "r2", "l1"]
    assert [row["signal_source"] for row in result] == ["rating", "rating", "like"]
    assert result[-1]["signal_weight"] == recommender.PREF_SIGNAL_WEIGHT["like"]


def test_item_cf_caps_positive_signals_for_heavy_users():
    recommender = ItemCFRecommender()
    conn = _FakeConn(
        [
            [
                {"mid": "r1", "rating": 5.0, "rated_at": "2026-03-10 10:00:00"},
                {"mid": "r2", "rating": 4.5, "rated_at": "2026-03-09 10:00:00"},
                {"mid": "r3", "rating": 4.0, "rated_at": "2026-03-08 10:00:00"},
            ],
            [
                {"mid": "l1", "pref_type": "like", "created_at": "2026-03-10 12:00:00"},
                {"mid": "w1", "pref_type": "want_to_watch", "created_at": "2026-03-10 13:00:00"},
            ],
        ]
    )

    recommender.MAX_POSITIVE_RATING_SEEDS = 2
    recommender.MAX_LIKE_SEEDS = 1
    recommender.MAX_WISH_SEEDS = 0
    result = recommender.get_user_positive_movies(conn, user_id=1)

    assert [row["mid"] for row in result] == ["r1", "r2", "l1"]
    assert [row["signal_source"] for row in result] == ["rating", "rating", "like"]
    assert result[-1]["signal_weight"] == recommender.PREF_SIGNAL_WEIGHT["like"]
