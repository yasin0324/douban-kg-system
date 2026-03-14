"""
冷启动相关单元测试 — activity-summary + 算法偏好融合
"""

import pytest
from app.services import user_service
from app.algorithms.base import BaseRecommender


# ────────────── FakeConn / FakeCursor（复用 test_regressions 模式）──────────────

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


class FakeNeo4jSession:
    def __init__(self, records=None):
        self.records = list(records or [])
        self.calls = []

    def run(self, query, **params):
        self.calls.append((query, params))
        return list(self.records)


# ────────────── activity-summary 测试 ──────────────


def test_activity_summary_empty_user():
    """纯空用户 → effective_signal_count=0, cold_start=True"""
    cursor = FakeCursor(fetchall_results=[
        [],  # user_movie_ratings
        [],  # user_movie_prefs
    ])
    conn = FakeConn(cursor)

    result = user_service.get_activity_summary(conn, user_id=99)

    assert result["liked_count"] == 0
    assert result["want_to_watch_count"] == 0
    assert result["rating_count"] == 0
    assert result["effective_signal_count"] == 0
    assert result["cold_start"] is True
    assert result["meets_personalization_threshold"] is False


def test_activity_summary_only_likes():
    """仅 like 2 部 → effective_signal_count=2"""
    cursor = FakeCursor(fetchall_results=[
        [],  # ratings
        [{"mid": "m1", "pref_type": "like"}, {"mid": "m2", "pref_type": "like"}],
    ])
    conn = FakeConn(cursor)

    result = user_service.get_activity_summary(conn, user_id=1)

    assert result["liked_count"] == 2
    assert result["effective_signal_count"] == 2
    assert result["cold_start"] is True


def test_activity_summary_only_ratings():
    """仅评分 3 部 → effective_signal_count=3, cold_start=False"""
    cursor = FakeCursor(fetchall_results=[
        [{"mid": "m1"}, {"mid": "m2"}, {"mid": "m3"}],  # ratings
        [],  # prefs
    ])
    conn = FakeConn(cursor)

    result = user_service.get_activity_summary(conn, user_id=1)

    assert result["rating_count"] == 3
    assert result["effective_signal_count"] == 3
    assert result["cold_start"] is False
    assert result["meets_personalization_threshold"] is True


def test_activity_summary_dedup():
    """同一电影同时有评分和 like → effective_signal_count=1"""
    cursor = FakeCursor(fetchall_results=[
        [{"mid": "m1"}],  # ratings
        [{"mid": "m1", "pref_type": "like"}],  # prefs
    ])
    conn = FakeConn(cursor)

    result = user_service.get_activity_summary(conn, user_id=1)

    assert result["rating_count"] == 1
    assert result["liked_count"] == 1
    assert result["effective_signal_count"] == 1


def test_profile_analysis_summary_uses_deduplicated_signal_count():
    """画像摘要应沿用与 activity-summary 一致的去重冷启动口径"""
    cursor = FakeCursor(fetchall_results=[
        [{"mid": "m1", "rating": 4.0}],  # ratings
        [
            {"mid": "m1", "pref_type": "like"},
            {"mid": "m2", "pref_type": "want_to_watch"},
        ],
    ])
    conn = FakeConn(cursor)
    neo4j_session = FakeNeo4jSession()

    result = user_service.get_profile_analysis(conn, neo4j_session, user_id=1)

    assert result["summary"]["rating_count"] == 1
    assert result["summary"]["liked_count"] == 1
    assert result["summary"]["want_to_watch_count"] == 1
    assert result["summary"]["effective_signal_count"] == 2
    assert result["summary"]["cold_start"] is True
    assert result["summary"]["meets_personalization_threshold"] is False


# ────────────── 算法基类偏好融合测试 ──────────────

class DummyRecommender(BaseRecommender):
    name = "dummy"
    display_name = "Dummy"

    def recommend(self, user_id, n=20, exclude_mids=None, exclude_from_training=None):
        return []


def test_positive_movies_includes_prefs():
    """无评分只有 like → get_user_positive_movies 返回含合成评分 4.5 的条目"""
    cursor = FakeCursor(fetchall_results=[
        [],  # ratings (empty)
        [{"mid": "m1", "pref_type": "like"}, {"mid": "m2", "pref_type": "want_to_watch"}],
    ])
    conn = FakeConn(cursor)
    recommender = DummyRecommender()

    result = recommender.get_user_positive_movies(conn, user_id=1)

    mids = [str(r["mid"]) for r in result]
    assert "m1" in mids
    assert "m2" in mids
    # m1 (like → 4.5) should come before m2 (want_to_watch → 4.0)
    assert result[0]["rating"] == 4.5
    assert result[1]["rating"] == 4.0


def test_positive_movies_rating_takes_precedence():
    """同电影有评分(>=3.5)和 like → 使用真实评分，不叠加偏好"""
    cursor = FakeCursor(fetchall_results=[
        [{"mid": "m1", "rating": 4.0}],  # rating exists
        [{"mid": "m1", "pref_type": "like"}],  # also has like
    ])
    conn = FakeConn(cursor)
    recommender = DummyRecommender()

    result = recommender.get_user_positive_movies(conn, user_id=1)

    assert len(result) == 1
    assert result[0]["rating"] == 4.0  # real rating, not synthetic 4.5


def test_all_rated_mids_includes_prefs():
    """get_user_all_rated_mids 包含偏好电影"""
    cursor = FakeCursor(fetchall_results=[
        [{"mid": "m1"}],  # ratings
        [{"mid": "m2"}, {"mid": "m3"}],  # prefs
    ])
    conn = FakeConn(cursor)
    recommender = DummyRecommender()

    result = recommender.get_user_all_rated_mids(conn, user_id=1)

    assert result == {"m1", "m2", "m3"}
