import asyncio
import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.algorithms import graph_cf, graph_content, graph_ppr, hybrid_manager as hybrid_manager_module
from app.routers import recommend


class DummySession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyDriver:
    def session(self):
        return DummySession()


def load_evaluation_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_recommendations.py"
    spec = importlib.util.spec_from_file_location("evaluate_recommendations", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_graph_cf_uses_explicit_context_and_filters(monkeypatch):
    captured = {}

    def fake_run_query(session, query, timeout_ms=None, **params):
        captured["timeout_ms"] = timeout_ms
        captured["params"] = params
        return [{
            "movie_id": "m100",
            "title": "Movie 100",
            "cf_score": 7.5,
            "similar_user_count": 3,
            "strongest_similarity": 0.42,
        }]

    monkeypatch.setattr(graph_cf, "run_query", fake_run_query)
    monkeypatch.setattr(
        graph_cf,
        "fetch_movie_graph_profile_map",
        lambda driver, movie_ids, timeout_ms=None: {
            "m100": {
                "regions": {"美国"},
                "languages": {"英语"},
                "year": 2014,
                "rating": 8.1,
                "content_type": "movie",
                "votes": 8000,
                "genres": {"科幻"},
                "genre_names": ["科幻"],
                "directors": [],
                "director_ids": set(),
                "director_names": [],
                "actors": [],
                "actor_ids": set(),
                "actor_names": [],
            },
        },
    )
    monkeypatch.setattr(graph_cf.Neo4jConnection, "get_driver", lambda: DummyDriver())

    items = graph_cf._get_graph_cf_recommendations_sync(
        user_id=7,
        user_profile={
            "context_movie_ids": ["1", "1", "2"],
            "negative_movie_ids": ["7"],
            "positive_features": {"genres": {"科幻": 2.4}, "directors": {}, "actors": {}, "regions": {"美国": 1.2}, "languages": {"英语": 1.0}},
            "negative_features": {"genres": {}, "directors": {}, "actors": {}, "regions": {}, "languages": {}},
            "exploration_features": {"genres": {}, "directors": {}, "actors": {}},
            "positive_years": [2014],
            "positive_ratings": [8.3],
            "content_type_counter": {"movie": 1.0},
        },
        seen_movie_ids=["9", "9"],
        exclude_mock_users=True,
        limit=10,
        timeout_ms=600,
    )

    assert captured["timeout_ms"] == 600
    assert captured["params"]["positive_movie_ids"] == ["1", "2"]
    assert captured["params"]["negative_movie_ids"] == ["7"]
    assert captured["params"]["seen_movie_ids"] == ["9"]
    assert captured["params"]["exclude_mock_users"] is True
    assert captured["params"]["min_overlap"] == 1
    assert items[0]["movie_id"] == "m100"
    assert "相似用户" in items[0]["reasons"][0]


def test_graph_content_formats_weighted_reasons(monkeypatch):
    captured = {}

    def fake_run_query(session, query, timeout_ms=None, **params):
        captured["params"] = params
        return [{
            "movie_id": "m200",
            "title": "Movie 200",
            "matched_genres": ["科幻"],
            "matched_directors": [
                {"pid": "p1", "name": "诺兰"},
            ],
            "matched_actors": [],
        }]

    monkeypatch.setattr(graph_content, "run_query", fake_run_query)
    monkeypatch.setattr(
        graph_content,
        "fetch_movie_graph_profile_map",
        lambda driver, movie_ids, timeout_ms=None: {
            "m200": {
                "regions": {"美国"},
                "languages": {"英语"},
                "year": 2015,
                "rating": 8.3,
                "content_type": "movie",
                "votes": 9000,
                "genres": {"科幻"},
                "genre_names": ["科幻"],
                "directors": [{"pid": "p1", "name": "诺兰"}],
                "director_ids": {"p1"},
                "director_names": ["诺兰"],
                "actors": [],
                "actor_ids": set(),
                "actor_names": [],
            },
        },
    )
    monkeypatch.setattr(graph_content.Neo4jConnection, "get_driver", lambda: DummyDriver())

    items = graph_content._get_graph_content_recommendations_sync(
        user_id=7,
        user_profile={
            "positive_features": {
                "genres": {"科幻": 2.8},
                "directors": {"p1": 3.1},
                "actors": {},
                "regions": {"美国": 1.4},
                "languages": {"英语": 1.2},
            },
            "negative_features": {"genres": {}, "directors": {}, "actors": {}, "regions": {}, "languages": {}},
            "exploration_features": {"genres": {}, "directors": {}, "actors": {}},
            "positive_years": [2010, 2014],
            "positive_ratings": [8.5, 8.1],
            "content_type_counter": {"movie": 2.0},
        },
        seen_movie_ids=["30"],
        limit=5,
    )

    assert captured["params"]["genre_names"] == ["科幻"]
    assert captured["params"]["director_ids"] == ["p1"]
    assert captured["params"]["seen_movie_ids"] == ["30"]
    assert items[0]["movie_id"] == "m200"
    assert "命中偏好导演 诺兰" in items[0]["reasons"][0]
    assert "命中偏好类型 科幻" in items[0]["reasons"][1]


def test_graph_ppr_reranks_candidates_with_metadata_bonus(monkeypatch):
    monkeypatch.setattr(
        graph_ppr,
        "fetch_movie_graph_profile_map",
        lambda driver, movie_ids, timeout_ms=None: {
            "m1": {
                "regions": {"法国"},
                "languages": {"法语"},
                "year": 1994,
                "rating": 6.1,
                "content_type": "movie",
                "votes": 50,
                "genres": {"剧情"},
                "genre_names": ["剧情"],
                "directors": [],
                "director_ids": set(),
                "director_names": [],
                "actors": [],
                "actor_ids": set(),
                "actor_names": [],
            },
            "m2": {
                "regions": {"美国"},
                "languages": {"英语"},
                "year": 2015,
                "rating": 8.4,
                "content_type": "movie",
                "votes": 50000,
                "genres": {"科幻"},
                "genre_names": ["科幻"],
                "directors": [],
                "director_ids": set(),
                "director_names": [],
                "actors": [],
                "actor_ids": set(),
                "actor_names": [],
            },
        },
    )

    items = graph_ppr._rerank_ppr_records(
        driver=None,
        user_profile={
            "positive_features": {"genres": {"科幻": 3.0}, "directors": {}, "actors": {}, "regions": {"美国": 2.0}, "languages": {"英语": 1.5}},
            "negative_features": {"genres": {}, "directors": {}, "actors": {}, "regions": {}, "languages": {}},
            "exploration_features": {"genres": {}, "directors": {}, "actors": {}},
            "positive_years": [2014],
            "positive_ratings": [8.5],
            "content_type_counter": {"movie": 1.0},
        },
        records=[
            {"movie_id": "m1", "title": "Movie 1", "ppr_score": 0.50},
            {"movie_id": "m2", "title": "Movie 2", "ppr_score": 0.45},
        ],
        timeout_ms=1000,
        base_reason="通过图谱连接发现",
    )

    assert items[0]["movie_id"] == "m2"
    assert "偏好类型 科幻" in items[0]["reasons"][1]


def test_hybrid_manager_reweights_when_branch_times_out(monkeypatch):
    manager = hybrid_manager_module.HybridRecommendationManager(
        branch_timeouts_ms={"graph_cf": 100, "graph_content": 100, "graph_ppr": 10},
    )

    async def fake_cf(**kwargs):
        return [
            {"movie_id": "m1", "title": "Movie 1", "score": 9.0, "reasons": ["cf"], "source": "graph_cf"},
            {"movie_id": "m2", "title": "Movie 2", "score": 5.0, "reasons": ["cf"], "source": "graph_cf"},
        ]

    async def fake_content(**kwargs):
        return []

    async def fake_ppr(**kwargs):
        await asyncio.sleep(0.05)
        return [{"movie_id": "m3", "title": "Movie 3", "score": 1.0, "reasons": ["ppr"], "source": "graph_ppr"}]

    monkeypatch.setattr(hybrid_manager_module, "get_graph_cf_recommendations", fake_cf)
    monkeypatch.setattr(hybrid_manager_module, "get_graph_content_recommendations", fake_content)
    monkeypatch.setattr(hybrid_manager_module, "get_graph_ppr_recommendations", fake_ppr)

    items = asyncio.run(
        manager.get_hybrid_recommendations(
            user_id=1,
            user_profile={"context_movie_ids": ["10", "20"]},
            seen_movie_ids=["30"],
            limit=5,
        )
    )

    assert items[0]["movie_id"] == "m1"
    assert items[0]["final_score"] == 1.0
    assert items[0]["source_algorithms"] == ["graph_cf"]
    assert items[0]["score_breakdown"] == {"graph_cf": 1.0}
    assert items[1]["final_score"] == 0.0
    assert items[1]["source_algorithms"] == ["graph_cf"]
    assert items[1]["score_breakdown"] == {"graph_cf": 0.0}


def test_recommend_route_keeps_response_shape(monkeypatch):
    app = FastAPI()
    app.include_router(recommend.router)

    def override_current_user():
        return {"id": 9}

    def override_conn():
        yield object()

    captured = {}

    async def fake_payload(**kwargs):
        captured.update(kwargs)
        return {
            "algorithm": "hybrid",
            "cold_start": False,
            "generation_mode": "profile",
            "profile_summary": {"rating_count": 4, "likes": 1, "wants": 2},
            "profile_highlights": [{"type": "genre", "label": "科幻"}],
            "items": [{
                "movie": {"mid": "m9", "title": "Movie 9"},
                "score": 0.93,
                "reasons": ["cf"],
                "source_algorithms": ["cf"],
                "score_breakdown": {"cf": 0.93},
            }],
        }

    app.dependency_overrides[recommend.get_current_user] = override_current_user
    app.dependency_overrides[recommend.get_mysql_conn] = override_conn
    monkeypatch.setattr(
        recommend.recommend_service,
        "build_personal_recommendation_payload",
        fake_payload,
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/recommend/personal?algorithm=hybrid&limit=5&exclude_movie_ids=1&exclude_movie_ids=2&reroll_token=reroll-1",
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["algorithm"] == "hybrid"
    assert payload["generation_mode"] == "profile"
    assert payload["profile_highlights"] == [{"type": "genre", "label": "科幻"}]
    assert payload["items"][0]["movie"] == {"mid": "m9", "title": "Movie 9"}
    assert payload["items"][0]["score_breakdown"] == {"cf": 0.93}
    assert captured["user_id"] == 9
    assert captured["exclude_movie_ids"] == ["1", "2"]
    assert captured["reroll_token"] == "reroll-1"


def test_recommend_explain_route_returns_graph_payload(monkeypatch):
    app = FastAPI()
    app.include_router(recommend.router)

    def override_current_user():
        return {"id": 12}

    def override_conn():
        yield object()

    captured = {}

    def fake_explain(**kwargs):
        captured.update(kwargs)
        return {
            "algorithm": "cf",
            "target_movie": {"mid": "m9", "title": "Movie 9"},
            "representative_movies": [{"mid": "1", "title": "Seed 1"}],
            "profile_highlights": [{"type": "genre", "label": "科幻"}],
            "profile_reasons": ["偏好类型 科幻"],
            "negative_signals": [],
            "nodes": [{"id": "movie_m9", "label": "Movie 9", "type": "Movie"}],
            "edges": [],
            "reason_paths": [],
            "matched_entities": [],
            "meta": {"has_graph_evidence": False, "representative_movie_count": 1},
        }

    app.dependency_overrides[recommend.get_current_user] = override_current_user
    app.dependency_overrides[recommend.get_mysql_conn] = override_conn
    monkeypatch.setattr(
        recommend.recommend_service,
        "build_recommendation_explain_payload",
        fake_explain,
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/recommend/explain?target_mid=m9&algorithm=cf",
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target_movie"]["mid"] == "m9"
    assert payload["meta"]["has_graph_evidence"] is False
    assert captured["user_id"] == 12
    assert captured["target_mid"] == "m9"
    assert captured["algorithm"] == "cf"
    assert captured["conn"] is not None


def test_time_split_case_avoids_holdout_leakage():
    evaluation = load_evaluation_module()
    rows = [
        {"user_id": 1, "mid": "a", "rating": 5.0},
        {"user_id": 1, "mid": "b", "rating": 3.0},
        {"user_id": 1, "mid": "c", "rating": 4.0},
        {"user_id": 1, "mid": "d", "rating": 2.0},
    ]

    case = evaluation.build_time_split_case(rows)

    assert case["holdout_movie_id"] == "c"
    assert case["seed_movie_ids"] == ["a"]
    assert case["seen_movie_ids"] == ["a", "b"]
    assert evaluation.hit_at_k([{"movie_id": "c"}], "c", 10) == 1.0
