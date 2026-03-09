from fastapi.testclient import TestClient

from app.algorithms import common
from app import main as app_main
from app.recommendation_cache import get_user_profile_cache, set_user_profile_cache
from app.services import recommend_service, user_service


class DummySession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self.last_query = query
        self.last_params = params
        return []


class DummyDriver:
    def session(self):
        return DummySession()


class DummyCursor:
    def __init__(self, fetchone_rows=None, fetchall_rows=None, rowcount=1):
        self._fetchone_rows = list(fetchone_rows or [])
        self._fetchall_rows = list(fetchall_rows or [])
        self.rowcount = rowcount
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params):
        self.executed.append((query, params))

    def fetchone(self):
        if self._fetchone_rows:
            return self._fetchone_rows.pop(0)
        return None

    def fetchall(self):
        return list(self._fetchall_rows)


class DummyConn:
    def __init__(self, cursor_factory):
        self._cursor_factory = cursor_factory
        self.commit_count = 0

    def cursor(self):
        return self._cursor_factory()

    def commit(self):
        self.commit_count += 1


def test_build_user_profile_uses_cache(monkeypatch):
    call_count = {"profile": 0}

    def fake_build_user_recommendation_profile(conn, user_id):
        call_count["profile"] += 1
        return {
            "movie_feedback": {
                "m1": {"positive_weight": 1.0, "negative_weight": 0.0, "exploration_weight": 0.0},
            },
            "positive_movie_ids": ["m1"],
            "negative_movie_ids": [],
            "representative_movie_ids": ["m1"],
            "context_movie_ids": ["m1"],
            "graph_context_movie_ids": ["m1"],
            "hard_exclude_movie_ids": ["m1"],
            "summary": {"cold_start": False},
        }

    monkeypatch.setattr(user_service, "build_user_recommendation_profile", fake_build_user_recommendation_profile)
    monkeypatch.setattr(
        recommend_service,
        "fetch_movie_graph_profile_map",
        lambda driver, movie_ids, timeout_ms=None: {
            "m1": {
                "regions": {"美国"},
                "languages": {"英语"},
                "year": 2014,
                "rating": 8.1,
                "content_type": "movie",
                "votes": 1000,
                "genres": {"科幻"},
                "genre_names": ["科幻"],
                "directors": [],
                "director_ids": set(),
                "director_names": [],
                "actors": [],
                "actor_ids": set(),
                "actor_names": [],
            }
        },
    )
    monkeypatch.setattr(recommend_service.Neo4jConnection, "get_driver", lambda: DummyDriver())

    first = recommend_service._build_user_profile(object(), 7)
    second = recommend_service._build_user_profile(object(), 7)

    assert first["profile_highlights"] == [{"type": "genre", "label": "科幻"}, {"type": "region", "label": "美国"}]
    assert second["profile_highlights"] == first["profile_highlights"]
    assert call_count["profile"] == 1


def test_preference_mutations_invalidate_user_profile_cache():
    set_user_profile_cache(11, {"summary": {"cold_start": False}})

    add_conn = DummyConn(
        lambda: DummyCursor(fetchone_rows=[{"id": 1, "mid": "m1", "pref_type": "like", "created_at": "2026-03-08"}])
    )
    user_service.add_preference(add_conn, 11, "m1", "like")

    assert get_user_profile_cache(11) is None

    set_user_profile_cache(11, {"summary": {"cold_start": False}})
    remove_conn = DummyConn(lambda: DummyCursor(rowcount=1))
    assert user_service.remove_preference(remove_conn, 11, "m1") is True
    assert get_user_profile_cache(11) is None


def test_rating_mutations_invalidate_user_profile_cache(monkeypatch):
    monkeypatch.setattr(user_service, "check_movie_released", lambda conn, mid: None)
    monkeypatch.setattr(user_service.Neo4jConnection, "get_driver", lambda: DummyDriver())

    set_user_profile_cache(21, {"summary": {"cold_start": False}})
    add_conn = DummyConn(
        lambda: DummyCursor(fetchone_rows=[{"id": 1, "mid": "m1", "rating": 4.5, "comment_short": None, "rated_at": "2026-03-08"}])
    )
    user_service.add_rating(add_conn, 21, "m1", 4.5)

    assert get_user_profile_cache(21) is None

    set_user_profile_cache(21, {"summary": {"cold_start": False}})
    remove_conn = DummyConn(lambda: DummyCursor(rowcount=1))
    assert user_service.remove_rating(remove_conn, 21, "m1") is True
    assert get_user_profile_cache(21) is None


def test_fetch_movie_brief_map_uses_cache(monkeypatch):
    call_count = {"count": 0}

    def fake_run_query(session, query, timeout_ms=None, **params):
        call_count["count"] += 1
        return [
            {
                "requested_id": "m1",
                "mid": "m1",
                "title": "Movie 1",
                "rating": 8.4,
                "year": 2024,
                "cover": "cover-1.jpg",
                "genres": ["科幻"],
            }
        ]

    monkeypatch.setattr(recommend_service, "run_query", fake_run_query)
    monkeypatch.setattr(recommend_service.Neo4jConnection, "get_driver", lambda: DummyDriver())

    first = recommend_service._fetch_movie_brief_map(["m1"], timeout_ms=600)
    second = recommend_service._fetch_movie_brief_map(["m1"], timeout_ms=600)

    assert first["m1"]["title"] == "Movie 1"
    assert second["m1"]["cover"] == "cover-1.jpg"
    assert call_count["count"] == 1


def test_fetch_movie_graph_profile_map_uses_cache(monkeypatch):
    call_count = {"count": 0}

    def fake_run_query(session, query, timeout_ms=None, **params):
        call_count["count"] += 1
        return [
            {
                "movie_id": "m1",
                "regions": "美国",
                "languages": "英语",
                "year": 2024,
                "rating": 8.2,
                "content_type": "movie",
                "votes": 12345,
                "genres": ["科幻"],
                "directors": [{"pid": "p1", "name": "诺兰"}],
                "actors": [{"pid": "a1", "name": "演员 A"}],
            }
        ]

    monkeypatch.setattr(common, "run_query", fake_run_query)

    first = common.fetch_movie_graph_profile_map(DummyDriver(), ["m1"], timeout_ms=800)
    second = common.fetch_movie_graph_profile_map(DummyDriver(), ["m1"], timeout_ms=800)

    assert first["m1"]["director_ids"] == {"p1"}
    assert second["m1"]["actor_names"] == ["演员 A"]
    assert call_count["count"] == 1


def test_app_lifespan_continues_when_cfkg_prewarm_fails(monkeypatch):
    calls = []

    monkeypatch.setattr(app_main, "init_pool", lambda: calls.append("init_pool"))
    monkeypatch.setattr(app_main, "close_pool", lambda: calls.append("close_pool"))
    monkeypatch.setattr(app_main.Neo4jConnection, "get_driver", lambda: calls.append("neo4j_driver") or object())
    monkeypatch.setattr(app_main.Neo4jConnection, "close", lambda: calls.append("neo4j_close"))

    async def fake_prewarm():
        calls.append("prewarm")
        raise RuntimeError("boom")

    monkeypatch.setattr(app_main, "prewarm_cfkg_model", fake_prewarm)

    with TestClient(app_main.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert "prewarm" in calls
    assert "init_pool" in calls
    assert "close_pool" in calls
