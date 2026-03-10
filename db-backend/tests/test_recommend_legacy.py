from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import recommend


def override_current_user():
    return {"id": 7}


def build_client():
    app = FastAPI()
    app.include_router(recommend.router)
    app.dependency_overrides[recommend.get_current_user] = override_current_user
    return TestClient(app)


def test_personal_recommendation_route_returns_disabled_stub_payload():
    with build_client() as client:
        response = client.get(
            "/api/recommend/personal?algorithm=HYBRID&limit=5&exclude_movie_ids=1&exclude_movie_ids=2&reroll_token=reroll-1"
        )

    assert response.status_code == 200
    assert response.json() == {
        "algorithm": "hybrid",
        "cold_start": True,
        "generation_mode": "disabled",
        "profile_summary": {
            "rating_count": 0,
            "strong_positive_ratings": 0,
            "weak_positive_ratings": 0,
            "weak_negative_ratings": 0,
            "likes": 0,
            "wants": 0,
            "positive_movie_count": 0,
            "behavior_movie_count": 0,
            "cold_start": True,
        },
        "profile_highlights": [],
        "items": [],
        "disabled": True,
        "message": "recommendation backend removed",
    }


def test_recommendation_explain_route_returns_disabled_stub_payload():
    with build_client() as client:
        response = client.get("/api/recommend/explain?target_mid=1297747&algorithm=CFKG")

    assert response.status_code == 200
    assert response.json() == {
        "algorithm": "cfkg",
        "target_movie": {
            "mid": "1297747",
            "title": "",
            "rating": None,
            "year": None,
            "cover": None,
            "genres": [],
        },
        "representative_movies": [],
        "profile_highlights": [],
        "profile_reasons": [],
        "negative_signals": [],
        "nodes": [],
        "edges": [],
        "reason_paths": [],
        "matched_entities": [],
        "meta": {
            "has_graph_evidence": False,
            "representative_movie_count": 0,
            "cold_start": True,
        },
        "disabled": True,
        "message": "recommendation backend removed",
    }
