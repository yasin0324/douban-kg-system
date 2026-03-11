"""
推荐路由测试 — 验证新的推荐系统路由基本结构

注意: 这些测试使用 mock 数据，不依赖真实数据库连接
"""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import recommend


def override_current_user():
    return {"id": 7, "username": "test", "nickname": "Test", "email": "test@test.com", "status": "active"}


def build_client():
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
    algo_names = [a["name"] for a in data["algorithms"]]
    assert "content" in algo_names
    assert "item_cf" in algo_names
    assert "kg_path" in algo_names
    assert "kg_embed" in algo_names


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
