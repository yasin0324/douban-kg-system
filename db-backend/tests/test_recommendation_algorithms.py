import numpy as np
import pytest

from app.algorithms.graph_cache import (
    GraphMetadataCache,
    MovieGraphProfile,
)
from app.algorithms.kg_embed import KGEmbedRecommender
from app.algorithms.kg_path import KGPathRecommender


def setup_function():
    GraphMetadataCache.clear()


def teardown_function():
    GraphMetadataCache.clear()


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
