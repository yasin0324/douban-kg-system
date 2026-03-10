from fastapi import FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app import dependencies
from app.routers import users
from app.services import admin_service, person_service, user_service


class FakeCursor:
    def __init__(self, fetchone_results=None, fetchall_results=None, rowcount=0):
        self.fetchone_results = list(fetchone_results or [])
        self.fetchall_results = list(fetchall_results or [])
        self.queries = []
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.queries.append((sql, params))

    def fetchone(self):
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return None

    def fetchall(self):
        if self.fetchall_results:
            return self.fetchall_results.pop(0)
        return []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConn:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor
        self.commit_called = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commit_called += 1


def test_get_current_user_requires_sid(monkeypatch):
    monkeypatch.setattr(dependencies, "_decode_token", lambda _token: {"sub": "1", "type": "access"})

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    conn = FakeConn(FakeCursor())

    try:
        dependencies.get_current_user(credentials=credentials, conn=conn)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail == "Token 无效"


def test_ban_user_nonexistent_target():
    conn = FakeConn(FakeCursor(fetchone_results=[None]))
    try:
        admin_service.ban_user(conn, admin_id=1, user_id=999)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "用户不存在"
    assert conn.commit_called == 0


def test_search_persons_uses_person_table():
    cursor = FakeCursor(
        fetchone_results=[{"total": 1}],
        fetchall_results=[[{"pid": "1001", "name": "Alice", "profession": "演员"}]],
    )
    conn = FakeConn(cursor)

    result = person_service.search_persons(conn, "Ali", page=1, size=20)

    assert result["total"] == 1
    assert result["items"][0]["pid"] == "1001"
    assert any("FROM person" in sql for sql, _ in cursor.queries)
    assert not any("FROM persons" in sql for sql, _ in cursor.queries)


def test_get_rating_returns_empty_payload_when_user_has_not_rated(monkeypatch):
    app = FastAPI()
    app.include_router(users.router)

    def override_current_user():
        return {"id": 7}

    def override_conn():
        yield object()

    app.dependency_overrides[users.get_current_user] = override_current_user
    app.dependency_overrides[users.get_mysql_conn] = override_conn
    monkeypatch.setattr(users.user_service, "get_rating", lambda conn, user_id, mid: None)

    with TestClient(app) as client:
        response = client.get("/api/users/ratings/1297747")

    assert response.status_code == 200
    assert response.json() == {
        "mid": "1297747",
        "has_rating": False,
        "id": None,
        "rating": None,
        "comment_short": None,
        "rated_at": None,
    }


def test_add_preference_commits_without_recommendation_side_effects():
    cursor = FakeCursor(fetchone_results=[{"id": 1, "mid": "m1", "pref_type": "like", "created_at": "2026-03-10"}])
    conn = FakeConn(cursor)

    payload = user_service.add_preference(conn, user_id=7, mid="m1", pref_type="like")

    assert conn.commit_called == 1
    assert payload["pref_type"] == "like"
    assert any("INSERT INTO user_movie_prefs" in sql for sql, _ in cursor.queries)


def test_remove_preference_returns_true_without_recommendation_side_effects():
    cursor = FakeCursor(rowcount=1)
    conn = FakeConn(cursor)

    ok = user_service.remove_preference(conn, user_id=7, mid="m1")

    assert ok is True
    assert conn.commit_called == 1


def test_add_rating_commits_without_neo4j_or_recommendation_side_effects(monkeypatch):
    monkeypatch.setattr(user_service, "check_movie_released", lambda conn, mid: None)
    cursor = FakeCursor(fetchone_results=[{"id": 1, "mid": "m1", "rating": 4.5, "comment_short": None, "rated_at": "2026-03-10"}])
    conn = FakeConn(cursor)

    payload = user_service.add_rating(conn, user_id=7, mid="m1", rating=4.5)

    assert conn.commit_called == 1
    assert payload["rating"] == 4.5
    assert any("INSERT INTO user_movie_ratings" in sql for sql, _ in cursor.queries)


def test_remove_rating_returns_true_without_neo4j_or_recommendation_side_effects():
    cursor = FakeCursor(rowcount=1)
    conn = FakeConn(cursor)

    ok = user_service.remove_rating(conn, user_id=7, mid="m1")

    assert ok is True
    assert conn.commit_called == 1
