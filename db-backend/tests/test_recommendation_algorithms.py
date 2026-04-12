import numpy as np
import pytest
from unittest.mock import patch

from app.algorithms.cfkg import CFKGRecommender
from app.algorithms.graph_cache import (
    GraphMetadataCache,
    MovieGraphProfile,
    RATED_POSITIVE_RELATION,
    RATED_POSITIVE_RELATION_REV,
    REL_ACTOR,
    REL_CONTENT_TYPE,
    REL_DIRECTOR,
    REL_LANGUAGE,
    REL_REGION,
    REL_YEAR_BUCKET,
)
from app.algorithms.item_cf import ItemCFRecommender
from app.algorithms.kg_embed import KGEmbedRecommender
from app.algorithms.kg_path import KGPathRecommender, REL_SHARED_AUDIENCE


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


def test_graph_cache_build_triples_can_include_user_positive_relations_and_holdouts(monkeypatch):
    GraphMetadataCache._loaded = True
    GraphMetadataCache._movie_profiles = {
        "m1": MovieGraphProfile(mid="m1", name="Movie 1"),
        "m2": MovieGraphProfile(mid="m2", name="Movie 2"),
    }
    GraphMetadataCache._movie_mids = ["m1", "m2"]
    GraphMetadataCache._movie_name_map = {"m1": "Movie 1", "m2": "Movie 2"}
    GraphMetadataCache._triples_cache = {}

    rating_rows = [
        {"user_id": 1, "mid": "m1", "rating": 5.0},
        {"user_id": 1, "mid": "m2", "rating": 4.0},
        {"user_id": 2, "mid": "m2", "rating": 4.5},
    ]
    pref_rows = [
        {"user_id": 2, "mid": "m1", "pref_type": "like"},
        {"user_id": 3, "mid": "m1", "pref_type": "want_to_watch"},
    ]

    class FakeCursor:
        def __init__(self):
            self._result = []

        def execute(self, query, params=()):
            if "FROM user_movie_ratings" in query:
                self._result = rating_rows
            elif "FROM user_movie_prefs" in query:
                self._result = pref_rows
            else:
                raise AssertionError(query)

        def fetchall(self):
            return list(self._result)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr("app.algorithms.graph_cache.get_connection", lambda: FakeConn())

    triples, _, entity_types, relation_types = GraphMetadataCache.build_triples(
        include_user_positive_relations=True,
        user_source="public",
        holdout_positive_by_user={"1": "m2"},
    )

    triple_set = set(triples)
    assert ("user_1", RATED_POSITIVE_RELATION, "movie_m1") in triple_set
    assert ("movie_m1", RATED_POSITIVE_RELATION_REV, "user_1") in triple_set
    assert ("user_1", RATED_POSITIVE_RELATION, "movie_m2") not in triple_set
    assert ("user_2", RATED_POSITIVE_RELATION, "movie_m2") in triple_set
    assert ("user_2", RATED_POSITIVE_RELATION, "movie_m1") in triple_set
    assert ("user_3", RATED_POSITIVE_RELATION, "movie_m1") not in triple_set
    assert relation_types[RATED_POSITIVE_RELATION] == ("user", "movie")
    assert relation_types[RATED_POSITIVE_RELATION_REV] == ("movie", "user")
    assert entity_types["user_1"] == "user"


def test_graph_cache_build_user_positive_path_index_respects_holdouts(monkeypatch):
    GraphMetadataCache._loaded = True
    GraphMetadataCache._movie_profiles = {
        "m1": MovieGraphProfile(mid="m1", name="Movie 1"),
        "m2": MovieGraphProfile(mid="m2", name="Movie 2"),
    }
    GraphMetadataCache._movie_mids = ["m1", "m2"]
    GraphMetadataCache._movie_name_map = {"m1": "Movie 1", "m2": "Movie 2"}
    GraphMetadataCache._user_positive_path_cache = {}

    rating_rows = [
        {"user_id": 1, "mid": "m1", "rating": 5.0},
        {"user_id": 1, "mid": "m2", "rating": 4.0},
        {"user_id": 2, "mid": "m2", "rating": 4.5},
    ]
    pref_rows = [
        {"user_id": 2, "mid": "m1", "pref_type": "like"},
        {"user_id": 3, "mid": "m1", "pref_type": "want_to_watch"},
    ]

    class FakeCursor:
        def __init__(self):
            self._result = []

        def execute(self, query, params=()):
            if "FROM user_movie_ratings" in query:
                self._result = rating_rows
            elif "FROM user_movie_prefs" in query:
                self._result = pref_rows
            else:
                raise AssertionError(query)

        def fetchall(self):
            return list(self._result)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr("app.algorithms.graph_cache.get_connection", lambda: FakeConn())

    user_to_movies, movie_to_users, user_positive_degree = GraphMetadataCache.build_user_positive_path_index(
        user_source="public",
        holdout_positive_by_user={"1": "m2"},
    )

    assert user_to_movies == {
        "1": {"m1": 1.0},
        "2": {"m1": 0.7, "m2": 0.9},
    }
    assert movie_to_users == {
        "m1": {"1": 1.0, "2": 0.7},
        "m2": {"2": 0.9},
    }
    assert user_positive_degree == {"1": 1, "2": 2}


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


def test_kg_embed_load_artifacts_includes_relation_indexes(tmp_path):
    embed_path = tmp_path / "embeddings.npz"
    meta_path = tmp_path / "meta.json"
    np.savez(
        embed_path,
        entity_embeddings=np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        relation_embeddings=np.array([[0.5, 0.5]], dtype=np.float32),
    )
    meta_path.write_text(
        '{"entity_to_idx":{"movie_m1":0,"user_1":1},'
        '"relation_to_idx":{"RATED_POSITIVE":0},'
        '"idx_to_entity":{"0":"movie_m1","1":"user_1"},'
        '"movie_mid_list":["m1"],'
        '"artifact_profile":{"holdout_positive_by_user":{"1":"m9"}}}',
        encoding="utf-8",
    )

    recommender = KGEmbedRecommender()
    artifacts = recommender._load_artifacts(str(embed_path), str(meta_path))

    assert artifacts["relation_embeddings"].shape == (1, 2)
    assert artifacts["relation_to_idx"][RATED_POSITIVE_RELATION] == 0
    assert artifacts["holdout_positive_by_user"] == {"1": "m9"}


def test_kg_embed_user_relation_components_use_user_and_relation_embeddings():
    recommender = KGEmbedRecommender(use_user_rating_relations=True)
    artifacts = {
        "movie_mid_list": ["m1", "m2"],
        "entity_to_idx": {"user_1": 0},
        "relation_to_idx": {RATED_POSITIVE_RELATION: 0},
        "entity_embeddings": np.array([[1.0, 0.0]], dtype=np.float32),
        "relation_embeddings": np.array([[0.0, 1.0]], dtype=np.float32),
        "movie_matrix": np.array(
            [
                [1 / np.sqrt(2), 1 / np.sqrt(2)],
                [0.0, 1.0],
            ],
            dtype=np.float32,
        ),
        "holdout_positive_by_user": {"1": "m9"},
    }

    scores = recommender._user_relation_components(
        user_id=1,
        artifacts=artifacts,
        exclude_from_training={"m9"},
    )

    assert scores[0] == pytest.approx(1.0, rel=1e-4)
    assert scores[1] == pytest.approx(1 / np.sqrt(2), rel=1e-4)


def test_kg_embed_user_relation_components_returns_zero_without_matching_holdout():
    recommender = KGEmbedRecommender(use_user_rating_relations=True)
    artifacts = {
        "movie_mid_list": ["m1"],
        "entity_to_idx": {"user_1": 0},
        "relation_to_idx": {RATED_POSITIVE_RELATION: 0},
        "entity_embeddings": np.array([[1.0, 0.0]], dtype=np.float32),
        "relation_embeddings": np.array([[0.0, 1.0]], dtype=np.float32),
        "movie_matrix": np.array([[1.0, 0.0]], dtype=np.float32),
        "holdout_positive_by_user": {},
    }

    scores = recommender._user_relation_components(
        user_id=1,
        artifacts=artifacts,
        exclude_from_training={"m9"},
    )

    assert np.count_nonzero(scores) == 0


def test_kg_embed_scope_changes_with_holdout_profile():
    recommender_a = KGEmbedRecommender(
        use_user_rating_relations=True,
        artifact_profile={
            "version": "offline_public_v1",
            "user_source": "public",
            "holdout_strategy": "last_positive_removed",
            "holdout_positive_by_user": {"1": "m1"},
        },
    )
    recommender_b = KGEmbedRecommender(
        use_user_rating_relations=True,
        artifact_profile={
            "version": "offline_public_v1",
            "user_source": "public",
            "holdout_strategy": "last_positive_removed",
            "holdout_positive_by_user": {"1": "m2"},
        },
    )

    assert recommender_a._scope_name() != recommender_b._scope_name()
    assert recommender_a._scope_name().startswith("expanded_userpos_public")


def test_kg_embed_score_candidates_respects_shortlist_and_exclusions(monkeypatch):
    recommender = KGEmbedRecommender()
    artifacts = {
        "movie_mid_list": ["m1", "m2", "m3"],
        "mid_to_movie_idx": {"m1": 0, "m2": 1, "m3": 2},
    }
    captured = {}

    monkeypatch.setattr(recommender, "_load_or_train", lambda: artifacts)
    monkeypatch.setattr(
        recommender,
        "_get_user_context",
        lambda user_id, exclude_from_training: ([{"mid": "seed"}], {"m1"}),
    )
    monkeypatch.setattr(
        recommender,
        "_get_user_components",
        lambda *args, **kwargs: {
            "user_relation_scores": np.zeros(3, dtype=np.float32),
            "centroid_scores": np.zeros(3, dtype=np.float32),
            "max_seed_scores": np.zeros(3, dtype=np.float32),
            "entity_overlap_scores": np.zeros(3, dtype=np.float32),
        },
    )

    def fake_build_ranked_results(*, artifacts, user_components, valid_mask, n):
        captured["valid_mask"] = valid_mask.copy()
        captured["n"] = n
        return [{"mid": "m2", "score": 1.0, "reason": "ok"}]

    monkeypatch.setattr(recommender, "_build_ranked_results", fake_build_ranked_results)

    results = recommender.score_candidates(
        user_id=1,
        candidate_mids=["m1", "m2", "m3"],
        exclude_from_training={"heldout"},
        exclude_mids={"m3"},
        n=2,
    )

    assert results == [{"mid": "m2", "score": 1.0, "reason": "ok"}]
    assert captured["valid_mask"].tolist() == [False, True, False]
    assert captured["n"] == 2


def test_kg_path_scoring_matches_manual_accumulation():
    recommender = KGPathRecommender(
        shared_audience_weight=0.6,
        director_weight=1.0,
        actor_weight=0.6,
        genre_weight=0.4,
        two_hop_weight=0.2,
        region_weight=0.1,
        language_weight=0.1,
        content_type_weight=0.05,
        year_bucket_weight=0.05,
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


def test_kg_path_shared_audience_records_penalize_heavy_bridge_users():
    recommender = KGPathRecommender(use_user_activity_penalty=True)

    records = recommender._build_shared_audience_records(
        user_id=1,
        seed_mid="seed",
        seed_weight=1.0,
        user_to_movies={
            "1": {"seed": 1.0, "seen": 1.0},
            "2": {"seed": 1.0, "cand_low": 1.0},
            "3": {"seed": 1.0, "cand_high": 1.0},
        },
        movie_to_users={"seed": {"1": 1.0, "2": 1.0, "3": 1.0}},
        user_positive_degree={"1": 2, "2": 2, "3": 20},
        per_seed_limit=10,
    )

    assert [record["mid"] for record in records] == ["cand_low", "cand_high"]
    assert records[0]["relation"] == REL_SHARED_AUDIENCE
    assert records[0]["strength"] > records[1]["strength"]
    assert all(record["mid"] != "seed" for record in records)


def test_kg_path_score_candidates_prunes_to_allowed_candidates(monkeypatch):
    recommender = KGPathRecommender()
    captured = {}

    monkeypatch.setattr(
        recommender,
        "_get_user_context",
        lambda user_id, exclude_from_training: ([{"mid": "seed"}], {"m1"}),
    )

    def fake_get_evidence_bundle(user_id, positive_movies, exclude_from_training, allowed_candidate_mids=None):
        captured["allowed_candidate_mids"] = allowed_candidate_mids
        return {
            "candidate_scores": {"m2": 2.0, "m3": 1.0},
            "candidate_paths": {"m2": 3, "m3": 1},
            "candidate_reasons": {"m2": ["reason 2"], "m3": ["reason 3"]},
        }

    monkeypatch.setattr(recommender, "_get_evidence_bundle", fake_get_evidence_bundle)

    results = recommender.score_candidates(
        user_id=1,
        candidate_mids=["m1", "m2", "m3"],
        exclude_from_training={"heldout"},
        exclude_mids={"m3"},
        n=5,
    )

    assert captured["allowed_candidate_mids"] == {"m2"}
    assert results == [{"mid": "m2", "score": 1.0, "reason": "reason 2", "path_count": 3}]


def test_kg_path_fetch_evidence_includes_expanded_one_hop_relations():
    recommender = KGPathRecommender(
        use_expanded_relations=True,
        use_user_behavior_paths=False,
        enable_two_hop=False,
    )
    GraphMetadataCache._loaded = True
    seed_profile = MovieGraphProfile(
        mid="seed",
        name="Seed",
        regions={"中国"},
        languages={"汉语"},
        content_type="movie",
        year_bucket="2010s",
    )
    candidate_profile = MovieGraphProfile(
        mid="cand",
        name="Candidate",
        regions={"中国"},
        languages={"汉语"},
        content_type="movie",
        year_bucket="2010s",
    )
    GraphMetadataCache._movie_profiles = {"seed": seed_profile, "cand": candidate_profile}
    GraphMetadataCache._relation_inverted_index = {
        REL_REGION: {"中国": {"seed", "cand"}},
        REL_LANGUAGE: {"汉语": {"seed", "cand"}},
        REL_CONTENT_TYPE: {"movie": {"seed", "cand"}},
        REL_YEAR_BUCKET: {"2010s": {"seed", "cand"}},
        REL_DIRECTOR: {},
        REL_ACTOR: {},
        "genre": {},
    }

    evidence = recommender._fetch_evidence_from_graph(
        user_id=1,
        seeds=[{"mid": "seed", "weight": 1.0}],
        actor_order_limit=5,
        include_two_hop=False,
        include_user_behavior_paths=False,
    )

    candidate_relations = {row["relation"] for row in evidence["candidate_evidence"]["cand"]}
    assert REL_REGION in candidate_relations
    assert REL_LANGUAGE in candidate_relations
    assert REL_CONTENT_TYPE in candidate_relations
    assert REL_YEAR_BUCKET in candidate_relations


def test_kg_path_shared_audience_reason_does_not_expose_user_ids():
    recommender = KGPathRecommender()

    reason = recommender._reason_for_record(
        {
            "relation": REL_SHARED_AUDIENCE,
            "entity_ids": ["2", "3"],
            "entity_names": [],
            "hits": 2,
        }
    )

    assert reason == "与多位同样喜欢该类电影的用户兴趣重合"
    assert "2" not in reason
    assert "3" not in reason


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


def test_kg_path_two_hop_prunes_to_informative_seed_and_bridge_actors():
    recommender = KGPathRecommender(
        two_hop_seed_actor_limit=1,
        two_hop_bridge_actor_limit=1,
    )
    GraphMetadataCache._loaded = True
    GraphMetadataCache._person_name_map = {"p1": "演员A", "p2": "演员B", "p3": "演员C", "p4": "演员D"}
    GraphMetadataCache._relation_degrees = {
        REL_ACTOR: {"p1": 100, "p2": 5, "p3": 80, "p4": 3}
    }
    seed_profile = MovieGraphProfile(
        mid="seed",
        name="Seed",
        actors={"p1", "p2"},
        top_actors={"p1", "p2"},
        actor_orders={"p1": 1, "p2": 2},
    )
    bridge_profile = MovieGraphProfile(
        mid="bridge",
        name="Bridge",
        actors={"p2", "p3", "p4"},
        top_actors={"p2", "p3", "p4"},
        actor_orders={"p2": 1, "p3": 2, "p4": 3},
    )
    candidate_profile = MovieGraphProfile(
        mid="cand",
        name="Candidate",
        actors={"p4"},
        top_actors={"p4"},
        actor_orders={"p4": 1},
    )

    records = recommender._build_two_hop_records(
        seed_mid="seed",
        seed_profile=seed_profile,
        seed_weight=1.0,
        actor_index={
            "p1": {"seed"},
            "p2": {"seed", "bridge"},
            "p3": {"bridge"},
            "p4": {"bridge", "cand"},
        },
        profiles={"seed": seed_profile, "bridge": bridge_profile, "cand": candidate_profile},
        per_seed_limit=10,
        actor_order_limit=5,
    )

    assert [record["mid"] for record in records] == ["cand"]
    assert records[0]["entity_ids"] == ["p4"]


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
    def __init__(self, rows, *, score_rows=None):
        self.rows = list(rows)
        self.score_rows = list(self.rows if score_rows is None else score_rows)
        self.recommend_calls = []
        self.score_candidate_calls = []

    def recommend(self, user_id, n=20, exclude_mids=None, exclude_from_training=None):
        self.recommend_calls.append(
            {
                "user_id": user_id,
                "n": n,
                "exclude_mids": exclude_mids,
                "exclude_from_training": exclude_from_training,
            }
        )
        return self.rows[:n]

    def score_candidates(self, user_id, candidate_mids, exclude_from_training=None, *, exclude_mids=None, n=None):
        self.score_candidate_calls.append(
            {
                "user_id": user_id,
                "candidate_mids": list(candidate_mids or []),
                "exclude_mids": exclude_mids,
                "exclude_from_training": exclude_from_training,
                "n": n,
            }
        )
        allowed = {str(mid) for mid in (candidate_mids or []) if mid}
        filtered = [row for row in self.score_rows if str(row.get("mid") or "") in allowed]
        if n is None:
            return filtered
        return filtered[:n]


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

    def close(self):
        return None


def test_item_cf_score_candidates_respects_shortlist_and_exclusions(monkeypatch):
    recommender = ItemCFRecommender()
    recommender._item_users = {
        "seed": {1: 5.0, 2: 4.0, 3: 5.0},
        "cand1": {2: 4.0, 3: 5.0},
        "cand2": {1: 4.0, 2: 4.0},
    }
    recommender._user_items = {
        1: ["seed", "cand2"],
        2: ["seed", "cand1", "cand2"],
        3: ["seed", "cand1"],
    }
    recommender._movie_names = {"seed": "Seed"}
    recommender._item_norms = {
        mid: np.sqrt(sum(value ** 2 for value in users.values()))
        for mid, users in recommender._item_users.items()
    }

    monkeypatch.setattr("app.algorithms.item_cf.get_connection", lambda: _FakeConn([]))
    monkeypatch.setattr(
        recommender,
        "get_user_positive_movies",
        lambda conn, user_id, threshold=3.5, exclude_mids=None: [{"mid": "seed", "signal_weight": 1.0}],
    )
    monkeypatch.setattr(
        recommender,
        "get_user_all_rated_mids",
        lambda conn, user_id, exclude_mids=None: {"seed"},
    )

    results = recommender.score_candidates(
        user_id=1,
        candidate_mids=["seed", "cand1", "cand2"],
        exclude_from_training={"heldout"},
        exclude_mids={"cand2"},
        n=None,
    )

    assert results == [
        {
            "mid": "cand1",
            "score": 1.0,
            "reason": "因为你喜欢《Seed》，推荐评分行为相似的电影",
        }
    ]


def test_cfkg_passes_branch_init_kwargs_to_internal_recommenders():
    recommender = CFKGRecommender(
        kg_embed_init_kwargs={"artifact_profile": {"user_source": "public"}},
        kg_path_init_kwargs={"behavior_profile": {"user_source": "public"}},
    )

    assert recommender._kg_embed._config["artifact_profile"] == {"user_source": "public"}
    assert recommender._kg_embed._config["use_user_rating_relations"] is True
    assert recommender._kg_path._config["behavior_profile"] == {"user_source": "public"}
    assert recommender._kg_path._config["use_user_behavior_paths"] is True
    assert recommender.EVAL_USE_CANDIDATE_SCORING is True
    assert recommender._config["item_cf_weight"] == pytest.approx(0.3)
    assert recommender._config["kg_embed_weight"] == pytest.approx(0.7)
    assert recommender._config["agreement_bonus"] == pytest.approx(0.02)
    assert recommender._config["kg_path_rerank_weight"] == pytest.approx(0.0)


def test_cfkg_parameter_grid_is_fixed_to_deliverable_config():
    grid = CFKGRecommender.parameter_grid()

    assert len(grid) == 1
    assert grid[0]["item_cf_weight"] == pytest.approx(0.3)
    assert grid[0]["kg_embed_weight"] == pytest.approx(0.7)
    assert grid[0]["agreement_bonus"] == pytest.approx(0.02)
    assert grid[0]["consensus_weight"] == pytest.approx(0.0)
    assert grid[0]["kg_path_rerank_weight"] == pytest.approx(0.0)
    assert grid[0]["content_fallback_weight"] == pytest.approx(0.0)


def test_cfkg_merges_candidates_and_prioritizes_kg_reasons():
    recommender = CFKGRecommender(kg_path_rerank_weight=0.05)
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

    assert [row["mid"] for row in results] == ["m1", "m3", "m2"]
    assert results[0]["source_algorithms"] == ["kg_embed", "item_cf", "kg_path"]
    assert results[0]["reasons"] == ["kg_path reason", "kg_embed reason", "item_cf reason"]
    assert results[0]["reason"] == "kg_path reason"
    assert recommender._kg_path.score_candidate_calls[0]["candidate_mids"] == ["m1", "m3", "m2"]


def test_cfkg_resolve_branch_weights_renormalizes_when_item_cf_missing():
    recommender = CFKGRecommender()

    weights = recommender._resolve_branch_weights(
        {
            "item_cf": [],
            "kg_embed": [{"mid": "m1", "score": 1.0, "reason": "kg"}],
        }
    )

    assert "item_cf" not in weights
    assert weights["kg_embed"] == pytest.approx(1.0)


def test_cfkg_agreement_bonus_only_applies_to_overlap():
    recommender = CFKGRecommender(agreement_bonus=0.05, consensus_weight=0.0)

    ranked = recommender._build_stage1_ranked(
        {
            "m1": {"scores": {"item_cf": 1.0, "kg_embed": 1.0}, "reasons": {}},
            "m2": {"scores": {"item_cf": 1.0}, "reasons": {}},
        },
        {"item_cf": 0.4, "kg_embed": 0.6},
    )

    scores = {item["mid"]: item["stage1_score"] for item in ranked}
    assert scores["m1"] == pytest.approx(1.0 + (0.4 / 0.6) + 0.05)
    assert scores["m2"] == pytest.approx(0.4)


def test_cfkg_consensus_contribution_uses_overlap_strength():
    recommender = CFKGRecommender(
        item_cf_weight=0.3,
        kg_embed_weight=0.7,
        agreement_bonus=0.0,
        consensus_weight=0.1,
        use_kg_path_explanations=False,
    )
    recommender._item_cf = StubRecommender(
        [],
        score_rows=[
            {"mid": "m1", "score": 0.9, "reason": "item 1"},
            {"mid": "m2", "score": 0.9, "reason": "item 2"},
        ],
    )
    recommender._kg_embed = StubRecommender(
        [],
        score_rows=[
            {"mid": "m1", "score": 0.95, "reason": "kg 1"},
            {"mid": "m2", "score": 0.2, "reason": "kg 2"},
        ],
    )
    recommender._kg_path = StubRecommender([])
    recommender._content = StubRecommender([])

    results = recommender.score_candidates(
        user_id=1,
        candidate_mids=["m1", "m2"],
        exclude_from_training={"heldout"},
        n=None,
    )

    assert [row["mid"] for row in results] == ["m1", "m2"]
    assert results[0]["source_algorithms"] == ["kg_embed", "item_cf"]
    assert results[0]["score"] > results[1]["score"]


def test_cfkg_branch_request_n_uses_full_list_for_offline_eval():
    recommender = CFKGRecommender(item_cf_recall=300)

    assert recommender._branch_request_n(300, 20) == 300
    assert recommender._branch_request_n(300, 99999) == 99999


def test_cfkg_score_candidates_ignores_recall_and_content_fallback():
    recommender = CFKGRecommender(
        item_cf_recall=1,
        kg_embed_recall=1,
        content_fallback_weight=0.9,
        agreement_bonus=0.0,
        use_kg_path_explanations=False,
    )
    recommender._item_cf = StubRecommender(
        [],
        score_rows=[
            {"mid": "m1", "score": 0.5, "reason": "item 1"},
            {"mid": "m2", "score": 1.0, "reason": "item 2"},
        ],
    )
    recommender._kg_embed = StubRecommender(
        [],
        score_rows=[
            {"mid": "m1", "score": 0.8, "reason": "kg 1"},
        ],
    )
    recommender._kg_path = StubRecommender([])
    recommender._content = StubRecommender(
        [{"mid": "m3", "score": 1.0, "reason": "content"}],
        score_rows=[{"mid": "m3", "score": 1.0, "reason": "content"}],
    )

    results = recommender.score_candidates(
        user_id=1,
        candidate_mids=["m1", "m2", "m3"],
        exclude_from_training={"heldout"},
        n=None,
    )

    assert [row["mid"] for row in results] == ["m1", "m2"]
    assert recommender._content.score_candidate_calls == []
    assert results[0]["reason"] == "kg 1"
    assert results[1]["reason"] == "item 2"


def test_cfkg_score_candidates_falls_back_to_item_cf_when_kg_embed_missing():
    recommender = CFKGRecommender(use_kg_path_explanations=False)
    recommender._item_cf = StubRecommender(
        [],
        score_rows=[{"mid": "m2", "score": 1.0, "reason": "item reason"}],
    )
    recommender._kg_embed = StubRecommender([], score_rows=[])
    recommender._kg_path = StubRecommender([])
    recommender._content = StubRecommender([])

    results = recommender.score_candidates(
        user_id=1,
        candidate_mids=["m1", "m2"],
        exclude_from_training={"heldout"},
        n=None,
    )

    assert results == [
        {
            "mid": "m2",
            "score": 1.0,
            "reason": "item reason",
            "reasons": ["item reason"],
            "source_algorithms": ["item_cf"],
        }
    ]


def test_cfkg_score_candidates_uses_kg_path_for_explanations_only():
    recommender = CFKGRecommender(
        item_cf_weight=0.2,
        kg_embed_weight=0.8,
        agreement_bonus=0.02,
        use_kg_path_explanations=True,
        kg_path_explain_topn=1,
    )
    recommender._item_cf = StubRecommender(
        [],
        score_rows=[{"mid": "m1", "score": 0.4, "reason": "item reason"}],
    )
    recommender._kg_embed = StubRecommender(
        [],
        score_rows=[{"mid": "m1", "score": 0.9, "reason": "kg reason"}],
    )
    recommender._kg_path = StubRecommender(
        [],
        score_rows=[{"mid": "m1", "score": 0.1, "reason": "kg_path explanation"}],
    )
    recommender._content = StubRecommender([])

    with_explain = recommender.score_candidates(
        user_id=1,
        candidate_mids=["m1"],
        exclude_from_training={"heldout"},
        n=None,
    )

    recommender.set_params(use_kg_path_explanations=False)
    without_explain = recommender.score_candidates(
        user_id=1,
        candidate_mids=["m1"],
        exclude_from_training={"heldout"},
        n=None,
    )

    assert with_explain[0]["score"] == without_explain[0]["score"]
    assert with_explain[0]["reason"] == "kg_path explanation"
    assert with_explain[0]["source_algorithms"] == ["kg_embed", "item_cf"]
    assert without_explain[0]["reason"] == "kg reason"


def test_cfkg_uses_content_as_fallback_candidates():
    recommender = CFKGRecommender(content_fallback_weight=0.05)
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


def test_cfkg_skips_rerank_when_weight_is_zero():
    recommender = CFKGRecommender(kg_path_rerank_weight=0.0)
    recommender._item_cf = StubRecommender([{"mid": "m1", "score": 0.9, "reason": "item"}])
    recommender._kg_embed = StubRecommender([{"mid": "m2", "score": 0.8, "reason": "embed"}])
    recommender._kg_path = StubRecommender(
        [],
        score_rows=[{"mid": "m1", "score": 1.0, "reason": "path"}],
    )
    recommender._content = StubRecommender([])

    results = recommender.recommend(user_id=1, n=5)

    assert [row["mid"] for row in results] == ["m2", "m1"]
    assert recommender._kg_path.score_candidate_calls == []


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
