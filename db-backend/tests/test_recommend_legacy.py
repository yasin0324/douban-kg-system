"""
推荐路由测试 — 验证新的推荐系统路由基本结构

注意: 这些测试使用 mock 数据，不依赖真实数据库连接
"""

import time
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import recommend


def override_current_user():
    return {"id": 7, "username": "test", "nickname": "Test", "email": "test@test.com", "status": "active"}


def build_client():
    recommend._reset_algorithm_runtime_state()
    app = FastAPI()
    app.include_router(recommend.router)
    app.dependency_overrides[recommend.get_current_user] = override_current_user
    return TestClient(app)


def test_algorithms_list_route():
    """测试算法列表接口"""
    with build_client() as client:
        response = client.get("/api/recommend/algorithms")

    assert response.status_code == 200
    data = response.json()
    assert "algorithms" in data
    algo_meta = {item["name"]: item for item in data["algorithms"]}
    algo_names = [a["name"] for a in data["algorithms"]]
    assert "cfkg" in algo_names
    assert "content" in algo_names
    assert "item_cf" in algo_names
    assert "kg_path" in algo_names
    assert "kg_embed" in algo_names
    assert algo_meta["cfkg"]["type"] == "KG"


@patch("app.algorithms.content_based.get_connection")
def test_personal_recommendation_empty_for_new_user(mock_conn):
    """测试新用户(无评分)返回空推荐"""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_connection = MagicMock()
    mock_connection.cursor.return_value = mock_cursor
    mock_conn.return_value = mock_connection

    with build_client() as client:
        response = client.get("/api/recommend/personal?algorithm=content&limit=5")

    assert response.status_code == 200
    data = response.json()
    assert data["algorithm"] == "content"
    assert data["cold_start"] is True
    assert data["items"] == []


def test_personal_recommendation_invalid_algorithm():
    """测试无效算法名返回 400"""
    with build_client() as client:
        response = client.get("/api/recommend/personal?algorithm=invalid_algo")

    assert response.status_code == 400


def test_evaluate_route_no_report():
    """测试评估接口在无报告时返回提示"""
    with build_client() as client:
        response = client.get("/api/recommend/evaluate")

    assert response.status_code == 200
    data = response.json()
    # 如果没有报告文件，应该返回提示信息
    assert "message" in data or "results" in data


def test_evaluate_route_falls_back_to_latest_history_report(tmp_path):
    fake_backend_root = tmp_path / "fake_backend"
    history_dir = fake_backend_root / "reports" / "history"
    history_dir.mkdir(parents=True)
    history_path = history_dir / "2026-03-12_101500_eval_results.json"
    history_path.write_text(
        '{"generated_at":"2026-03-12T10:15:00+08:00","results":{"kg_path":{"display_name":"KG"}}}',
        encoding="utf-8",
    )

    with patch.object(recommend, "__file__", str(fake_backend_root / "app" / "routers" / "recommend.py")):
        with build_client() as client:
            response = client.get("/api/recommend/evaluate")

    assert response.status_code == 200
    data = response.json()
    assert data["report_source"] == "2026-03-12_101500_eval_results.json"
    assert "kg_path" in data["results"]


def test_evaluate_route_prefers_latest_multi_algorithm_root_report(tmp_path):
    fake_backend_root = tmp_path / "fake_backend"
    reports_dir = fake_backend_root / "reports"
    history_dir = reports_dir / "history"
    history_dir.mkdir(parents=True)

    old_root = reports_dir / "eval_results.json"
    old_root.write_text(
        '{"generated_at":"2026-04-05T20:25:05+08:00","num_negatives":99,"selected_algorithms":["cfkg","content","item_cf","kg_path","kg_embed"],"results":{"cfkg":{"display_name":"CFKG"},"content":{"display_name":"Content"},"item_cf":{"display_name":"ItemCF"},"kg_path":{"display_name":"KG Path"},"kg_embed":{"display_name":"KG Embed"}}}',
        encoding="utf-8",
    )
    latest_root = reports_dir / "eval_results_neg499.json"
    latest_root.write_text(
        '{"generated_at":"2026-04-14T20:57:30+08:00","num_negatives":499,"selected_algorithms":["cfkg","content","item_cf","kg_path","kg_embed"],"results":{"cfkg":{"display_name":"CFKG"},"content":{"display_name":"Content"},"item_cf":{"display_name":"ItemCF"},"kg_path":{"display_name":"KG Path"},"kg_embed":{"display_name":"KG Embed"}}}',
        encoding="utf-8",
    )

    with patch.object(recommend, "__file__", str(fake_backend_root / "app" / "routers" / "recommend.py")):
        with build_client() as client:
            response = client.get("/api/recommend/evaluate")

    assert response.status_code == 200
    data = response.json()
    assert data["report_source"] == "eval_results_neg499.json"
    assert data["generated_at"] == "2026-04-14T20:57:30+08:00"
    assert data["num_negatives"] == 499


class SlowRecommender:
    display_name = "慢速推荐"

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def recommend(self, user_id: int, n: int = 20, exclude_mids=None, exclude_from_training=None):
        time.sleep(0.05)
        return []


class FastCFKGRecommender:
    display_name = "CFKG 主链路推荐"

    def recommend(self, user_id: int, n: int = 20, exclude_mids=None, exclude_from_training=None):
        return [
            {
                "mid": "m1",
                "score": 1.0,
                "reason": "kg reason",
                "reasons": ["kg reason", "cf reason"],
                "source_algorithms": ["cfkg", "kg_embed"],
            }
        ]


def test_personal_recommendation_defaults_to_cfkg():
    with (
        patch.object(recommend, "_get_algorithm_instance", return_value=FastCFKGRecommender()),
        patch.object(
            recommend,
            "_enrich_movie_details",
            return_value=[
                {
                    "movie": {"mid": "m1", "title": "Movie 1"},
                    "score": 1.0,
                    "reasons": ["kg reason", "cf reason"],
                    "source_algorithms": ["cfkg", "kg_embed"],
                }
            ],
        ),
    ):
        with build_client() as client:
            response = client.get("/api/recommend/personal?limit=5")

    assert response.status_code == 200
    data = response.json()
    assert data["algorithm"] == "cfkg"
    assert data["algorithm_display_name"] == "CFKG 主链路推荐"
    assert data["items"][0]["source_algorithms"] == ["cfkg", "kg_embed"]


def test_personal_recommendation_timeout_returns_504():
    with (
        patch.dict(recommend.ALGORITHMS, {"slow": SlowRecommender}, clear=False),
        patch.object(recommend, "RECOMMEND_TIMEOUT_SECONDS", 0.01),
    ):
        with build_client() as client:
            response = client.get("/api/recommend/personal?algorithm=slow&limit=5")

    assert response.status_code == 504
    assert "超时" in response.json()["detail"]
    time.sleep(0.06)
    recommend._reset_algorithm_runtime_state()


def test_personal_recommendation_recovers_after_timeout():
    with (
        patch.dict(recommend.ALGORITHMS, {"slow": SlowRecommender}, clear=False),
        patch.object(recommend, "RECOMMEND_TIMEOUT_SECONDS", 0.01),
    ):
        with build_client() as client:
            first_response = client.get("/api/recommend/personal?algorithm=slow&limit=5")
            second_response = client.get("/api/recommend/personal?algorithm=slow&limit=5")

    assert first_response.status_code == 504
    assert second_response.status_code == 504
    assert "超时" in second_response.json()["detail"]
    time.sleep(0.06)
    recommend._reset_algorithm_runtime_state()


def test_get_algorithm_instance_uses_online_safe_kwargs_for_kg_algorithms():
    class CaptureInitRecommender:
        display_name = "捕获初始化"

        def __init__(self, **kwargs):
            self.kwargs = kwargs

    recommend._reset_algorithm_runtime_state()
    with patch.dict(recommend.ALGORITHMS, {"kg_path": CaptureInitRecommender}, clear=False):
        algo = recommend._get_algorithm_instance("kg_path")

    assert algo.kwargs["use_expanded_relations"] is False
    assert algo.kwargs["enable_two_hop"] is False
    assert algo.kwargs["max_positive_rating_seeds"] == 8
    assert algo.kwargs["max_like_seeds"] == 4
    recommend._reset_algorithm_runtime_state()


def test_load_positive_movies_for_user_limits_explain_seed_count():
    mock_conn = MagicMock()
    algo = MagicMock()
    algo.get_user_positive_movies.return_value = [{"mid": f"m{i}"} for i in range(20)]

    with (
        patch.object(recommend, "_get_algorithm_instance", return_value=algo),
        patch.object(recommend, "get_connection", return_value=mock_conn),
    ):
        rows = recommend._load_positive_movies_for_user(7, "cfkg")

    assert len(rows) == recommend.EXPLAIN_MAX_POSITIVE_MOVIES
    mock_conn.close.assert_called_once()


def test_invalidate_recommendation_runtime_only_drops_affected_algorithms():
    recommend._reset_algorithm_runtime_state()
    with recommend._runtime_lock:
        recommend._algorithm_instances.update(
            {
                "cfkg": object(),
                "content": object(),
                "item_cf": object(),
                "kg_path": object(),
                "kg_embed": object(),
            }
        )

    recommend.invalidate_recommendation_runtime(preference_changed=True)

    with recommend._runtime_lock:
        assert "cfkg" not in recommend._algorithm_instances
        assert "kg_path" not in recommend._algorithm_instances
        assert "kg_embed" not in recommend._algorithm_instances
        assert "item_cf" in recommend._algorithm_instances
        assert "content" in recommend._algorithm_instances

    recommend.invalidate_recommendation_runtime(rating_changed=True)

    with recommend._runtime_lock:
        assert "item_cf" not in recommend._algorithm_instances
        assert "cfkg" not in recommend._algorithm_instances
        assert "content" in recommend._algorithm_instances

    recommend._reset_algorithm_runtime_state()
