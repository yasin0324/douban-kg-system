from app.algorithms.graph_cache import (
    GraphMetadataCache,
    MovieGraphProfile,
    REL_ACTOR,
    REL_DIRECTOR,
    REL_GENRE,
)
from app.routers import recommend


def setup_function():
    GraphMetadataCache.clear()


def teardown_function():
    GraphMetadataCache.clear()


def _prime_graph_cache(monkeypatch, profiles, person_names=None, relation_degrees=None):
    GraphMetadataCache._loaded = True
    GraphMetadataCache._movie_profiles = profiles
    GraphMetadataCache._movie_mids = sorted(profiles)
    GraphMetadataCache._movie_name_map = {
        mid: profile.name for mid, profile in profiles.items()
    }
    GraphMetadataCache._person_name_map = person_names or {}
    GraphMetadataCache._relation_degrees = relation_degrees or {
        REL_DIRECTOR: {},
        REL_ACTOR: {},
        REL_GENRE: {},
    }
    monkeypatch.setattr(GraphMetadataCache, "ensure_loaded", classmethod(lambda cls: None))


def test_build_recommendation_explain_payload_returns_signal_graph(monkeypatch):
    profiles = {
        "seed1": MovieGraphProfile(
            mid="seed1",
            name="Seed 1",
            year=2018,
            directors={"p1"},
            top_actors={"p2"},
            actor_orders={"p2": 1},
            genres={"剧情"},
        ),
        "target1": MovieGraphProfile(
            mid="target1",
            name="Target 1",
            year=2024,
            directors={"p1"},
            top_actors={"p2"},
            actor_orders={"p2": 1},
            genres={"剧情"},
        ),
    }
    _prime_graph_cache(
        monkeypatch,
        profiles,
        person_names={"p1": "导演甲", "p2": "演员乙"},
        relation_degrees={
            REL_DIRECTOR: {"p1": 3},
            REL_ACTOR: {"p2": 5},
            REL_GENRE: {"剧情": 10},
        },
    )

    payload = recommend._build_recommendation_explain_payload(
        target_movie={
            "mid": "target1",
            "title": "Target 1",
            "year": 2024,
            "rating": 8.6,
        },
        positive_movies=[{"mid": "seed1", "rating": 4.5}],
    )

    node_types = {node["type"] for node in payload["nodes"]}
    edge_types = {edge["type"] for edge in payload["edges"]}

    assert "Movie" in node_types
    assert "Signal" in node_types
    assert "SEED_CONTEXT" in edge_types
    assert "PROFILE_HINT" in edge_types
    assert payload["reason_paths"]
    assert payload["matched_entities"]


def test_build_recommendation_explain_payload_falls_back_to_target_context(monkeypatch):
    profiles = {
        "seed1": MovieGraphProfile(
            mid="seed1",
            name="Seed 1",
            year=2018,
            directors={"p9"},
            top_actors={"p8"},
            actor_orders={"p8": 1},
            genres={"悬疑"},
        ),
        "target1": MovieGraphProfile(
            mid="target1",
            name="Target 1",
            year=2024,
            directors={"p1"},
            top_actors={"p2"},
            actor_orders={"p2": 1},
            genres={"剧情"},
        ),
    }
    _prime_graph_cache(
        monkeypatch,
        profiles,
        person_names={"p1": "导演甲", "p2": "演员乙"},
    )

    payload = recommend._build_recommendation_explain_payload(
        target_movie={
            "mid": "target1",
            "title": "Target 1",
            "year": 2024,
            "rating": 8.6,
        },
        positive_movies=[{"mid": "seed1", "rating": 4.5}],
    )

    node_labels = {node["label"] for node in payload["nodes"]}
    edge_types = {edge["type"] for edge in payload["edges"]}

    assert "Target 1" in node_labels
    assert "导演甲" in node_labels
    assert "剧情" in node_labels
    assert "DIRECTED" in edge_types
    assert "HAS_GENRE" in edge_types
    assert payload["reason_paths"]
