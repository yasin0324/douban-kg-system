import asyncio
import importlib.util
from pathlib import Path

from app.algorithms import item_cf, tfidf_content
from app.services import recommend_service


def load_evaluation_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_recommendations.py"
    spec = importlib.util.spec_from_file_location("evaluate_recommendations", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_itemcf_recommendations_rank_collaborative_candidates(monkeypatch):
    def fake_get_similar_movies(conn, source_movie_id, limit=120):
        if source_movie_id == "s1":
            return [
                {
                    "movie_id": "c1",
                    "overlap_count": 6,
                    "source_user_count": 8,
                    "target_user_count": 12,
                    "similarity": 0.80,
                },
                {
                    "movie_id": "c2",
                    "overlap_count": 2,
                    "source_user_count": 8,
                    "target_user_count": 15,
                    "similarity": 0.15,
                },
            ]
        return [
            {
                "movie_id": "c1",
                "overlap_count": 4,
                "source_user_count": 6,
                "target_user_count": 12,
                "similarity": 0.45,
            }
        ]

    monkeypatch.setattr(item_cf, "_get_similar_movies", fake_get_similar_movies)
    monkeypatch.setattr(
        item_cf,
        "_fetch_movie_title_map",
        lambda conn, movie_ids: {"s1": "Seed 1", "s2": "Seed 2"},
    )

    items = item_cf._get_itemcf_recommendations_sync(
        conn=object(),
        user_id=1,
        user_profile={
            "context_movie_ids": ["s1", "s2"],
            "movie_feedback": {
                "s1": {"positive_weight": 2.0},
                "s2": {"positive_weight": 1.5},
            },
        },
        seen_movie_ids=["seen"],
        limit=5,
    )

    assert items[0]["movie_id"] == "c1"
    assert items[0]["support_movies"][0]["title"] == "Seed 1"
    assert "正向用户群高度重合" in items[0]["reasons"][0]


def test_tfidf_recommendations_surface_matched_terms(monkeypatch):
    bundle = {
        "movie_vectors": {
            "s1": {"genre:科幻": 0.8, "director:诺兰": 0.6},
            "s2": {"genre:悬疑": 0.9, "actor:周迅": 0.5},
            "c1": {"genre:科幻": 0.7, "director:诺兰": 0.7},
            "c2": {"genre:喜剧": 1.0},
        },
        "postings": {
            "genre:科幻": [("s1", 0.8), ("c1", 0.7)],
            "director:诺兰": [("s1", 0.6), ("c1", 0.7)],
            "genre:悬疑": [("s2", 0.9)],
            "actor:周迅": [("s2", 0.5)],
            "genre:喜剧": [("c2", 1.0)],
        },
        "title_map": {
            "s1": "种子电影 1",
            "s2": "种子电影 2",
            "c1": "候选电影 1",
            "c2": "候选电影 2",
        },
        "doc_count": 4,
    }
    monkeypatch.setattr(tfidf_content, "_get_or_build_bundle", lambda conn: bundle)

    items = tfidf_content._get_tfidf_recommendations_sync(
        conn=object(),
        user_id=1,
        user_profile={
            "context_movie_ids": ["s1", "s2"],
            "movie_feedback": {
                "s1": {"positive_weight": 2.0},
                "s2": {"positive_weight": 1.0},
            },
        },
        seen_movie_ids=["s1", "s2"],
        limit=5,
    )

    assert items[0]["movie_id"] == "c1"
    assert set(items[0]["matched_terms"][:2]) == {"导演:诺兰", "类型:科幻"}
    assert "命中文本/内容特征" in items[0]["reasons"][0]
    assert items[0]["support_movies"][0]["title"] == "种子电影 1"


def test_tfidf_explain_signals_expose_support_movies_and_terms(monkeypatch):
    bundle = {
        "movie_vectors": {
            "s1": {"genre:科幻": 0.8, "director:诺兰": 0.6},
            "target": {"genre:科幻": 0.6, "director:诺兰": 0.8},
        },
        "postings": {},
        "title_map": {"s1": "种子电影 1", "target": "目标电影"},
        "doc_count": 2,
    }
    monkeypatch.setattr(tfidf_content, "_get_or_build_bundle", lambda conn: bundle)

    payload = tfidf_content.build_tfidf_explain_signals(
        conn=object(),
        user_profile={
            "context_movie_ids": ["s1"],
            "movie_feedback": {"s1": {"positive_weight": 2.0}},
        },
        target_mid="target",
    )

    assert payload["matched_terms"][:2] == ["导演:诺兰", "类型:科幻"]
    assert payload["support_movies"][0]["movie_id"] == "s1"


def test_itemcf_empty_result_does_not_trigger_popularity_fallback(monkeypatch):
    monkeypatch.setattr(
        recommend_service,
        "_build_user_profile",
        lambda conn, user_id: {
            "movie_feedback": {},
            "positive_movie_ids": ["m1"],
            "negative_movie_ids": [],
            "representative_movie_ids": [],
            "context_movie_ids": ["m1"],
            "graph_context_movie_ids": ["m1"],
            "hard_exclude_movie_ids": ["m1"],
            "profile_highlights": [],
            "summary": {"cold_start": False},
        },
    )

    async def fake_dispatch(**kwargs):
        return []

    monkeypatch.setattr(recommend_service, "_dispatch_personal_algorithm", fake_dispatch)
    monkeypatch.setattr(recommend_service, "_fetch_movie_brief_map_safe", lambda conn, movie_ids, timeout_ms=None: {})
    monkeypatch.setattr(recommend_service, "_get_fallback_recommendations", lambda **kwargs: [{"movie_id": "hot"}])

    payload = asyncio.run(
        recommend_service.build_personal_recommendation_payload(
            conn=object(),
            user_id=1,
            algorithm="itemcf",
            limit=5,
        )
    )

    assert payload["algorithm"] == "itemcf"
    assert payload["cold_start"] is True
    assert payload["generation_mode"] == "cold_start"
    assert payload["items"] == []


def test_evaluation_metrics_and_report_generation(tmp_path, monkeypatch):
    evaluation = load_evaluation_module()
    items = [{"movie_id": "m1"}, {"movie_id": "m2"}, {"movie_id": "m3"}]
    relevant = {"m1", "m3"}
    genre_map = {
        "m1": {"科幻"},
        "m2": {"悬疑"},
        "m3": {"科幻", "悬疑"},
    }

    assert evaluation.precision_at_k(items, relevant, 2) == 0.5
    assert evaluation.recall_at_k(items, relevant, 3) == 1.0
    assert evaluation.ndcg_at_k(items, relevant, 3) > 0.9
    assert evaluation.diversity_at_k(items, genre_map, 3) > 0.0

    monkeypatch.setattr(evaluation, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(evaluation, "REPORT_JSON_PATH", tmp_path / "report.json")
    monkeypatch.setattr(evaluation, "REPORT_MD_PATH", tmp_path / "report.md")

    report = {
        "metadata": {
            "generated_at": "2026-03-09T12:00:00",
            "protocol_name": "profile_based_time_split",
            "user_limit": 10,
            "recommendation_limit": 20,
            "metric_k": 10,
            "algorithms": ["itemcf"],
            "catalog_movie_count": 100,
            "valid_case_count": 4,
        },
        "summary": {
            "itemcf": {
                "cases": 4,
                "failures": 0,
                "empty_cases": 1,
                "avg_candidates": 8.5,
                "precision_at_10": 0.15,
                "recall_at_10": 0.25,
                "ndcg_at_10": 0.18,
                "coverage": 0.2,
                "user_coverage": 0.75,
                "diversity": 0.5,
                "coverage_movie_count": 20,
            }
        },
        "raw_report": {},
    }
    json_path, md_path = evaluation.write_report_files(report)

    assert json_path.exists()
    assert md_path.exists()
    assert "Precision@10" in md_path.read_text(encoding="utf-8")


def test_strict_protocol_report_includes_protocol_notes(tmp_path, monkeypatch):
    evaluation = load_evaluation_module()
    monkeypatch.setattr(evaluation, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(evaluation, "REPORT_JSON_PATH", tmp_path / "report.json")
    monkeypatch.setattr(evaluation, "REPORT_MD_PATH", tmp_path / "report.md")

    report = {
        "metadata": {
            "generated_at": "2026-03-09T12:00:00",
            "protocol_name": "strict_profile_time_split",
            "protocol_notes": ["只使用严格早于切分时点的行为快照。"],
            "cfkg_evaluation_mode": "history_head_with_learned_reranker",
            "user_limit": 10,
            "recommendation_limit": 20,
            "metric_k": 10,
            "algorithms": ["cfkg"],
            "catalog_movie_count": 100,
            "valid_case_count": 4,
        },
        "summary": {
            "cfkg": {
                "cases": 4,
                "failures": 0,
                "empty_cases": 0,
                "avg_candidates": 8.5,
                "precision_at_10": 0.15,
                "recall_at_10": 0.25,
                "ndcg_at_10": 0.18,
                "coverage": 0.2,
                "user_coverage": 1.0,
                "diversity": 0.5,
                "coverage_movie_count": 20,
            }
        },
        "raw_report": {},
    }
    _, md_path = evaluation.write_report_files(report)
    markdown = md_path.read_text(encoding="utf-8")

    assert "严格协议附加说明" in markdown
    assert "learned reranker" in markdown


def test_build_strict_seed_context_preserves_order_and_filters_nonpositive():
    evaluation = load_evaluation_module()

    seed_rows, total_seed_weight = evaluation.build_strict_seed_context(
        positive_movie_ids=["s1", "s2", "s1", "s3", "s4"],
        positive_weights={
            "s1": 2.6,
            "s2": 0.0,
            "s3": -1.0,
            "s4": 1.9,
        },
    )

    assert seed_rows == [("s1", 2.6), ("s4", 1.9)]
    assert total_seed_weight == 4.5


def test_resolve_strict_graph_cf_context_prefers_ratings_and_likes_over_wants():
    evaluation = load_evaluation_module()

    movie_ids, weight_map = evaluation.resolve_strict_graph_cf_context(
        {
            "context_movie_ids": ["want_only", "liked", "rated"],
            "movie_feedback": {
                "want_only": {
                    "positive_weight": 0.8,
                    "is_want_to_watch": True,
                    "is_liked": False,
                    "rating": None,
                },
                "liked": {
                    "positive_weight": 1.9,
                    "is_want_to_watch": False,
                    "is_liked": True,
                    "rating": None,
                },
                "rated": {
                    "positive_weight": 2.6,
                    "is_want_to_watch": False,
                    "is_liked": False,
                    "rating": 4.0,
                },
            },
        }
    )

    assert movie_ids == ["liked", "rated"]
    assert weight_map == {"liked": 1.9, "rated": 2.6}


def test_merge_ranked_candidates_accumulates_multi_source_support():
    evaluation = load_evaluation_module()

    merged = evaluation.merge_ranked_candidates(
        [
            {"movie_id": "m1", "score": 0.7, "recall_score": 0.7, "source": "graph_cf", "source_algorithms": ["graph_cf"]},
        ],
        [
            {"movie_id": "m1", "score": 0.6, "recall_score": 0.6, "source": "itemcf", "source_algorithms": ["itemcf"]},
            {"movie_id": "m2", "score": 0.5, "recall_score": 0.5, "source": "itemcf", "source_algorithms": ["itemcf"]},
        ],
    )

    assert [item["movie_id"] for item in merged] == ["m1", "m2"]
    assert merged[0]["recall_score"] > 0.7
    assert merged[0]["source_algorithms"] == ["graph_cf", "itemcf"]


def test_strict_cfkg_recommendations_use_learned_reranker(monkeypatch):
    evaluation = load_evaluation_module()

    async def fake_collect_recall_candidates(**kwargs):
        return [
            {
                "movie_id": "m1",
                "title": "Movie 1",
                "score": 0.4,
                "recall_score": 0.4,
                "source": "graph_cf",
                "source_algorithms": ["graph_cf"],
                "reasons": ["cf recall"],
            },
            {
                "movie_id": "m2",
                "title": "Movie 2",
                "score": 0.4,
                "recall_score": 0.4,
                "source": "itemcf",
                "source_algorithms": ["graph_cf", "itemcf"],
                "reasons": ["itemcf recall"],
            },
        ]

    monkeypatch.setattr(
        evaluation,
        "load_cfkg_model_bundle",
        lambda model_path=None: {"path": "memory://cfkg"},
    )
    monkeypatch.setattr(
        evaluation,
        "collect_strict_cfkg_recall_candidates",
        fake_collect_recall_candidates,
    )
    monkeypatch.setattr(
        evaluation,
        "build_strict_cfkg_head_embedding",
        lambda bundle, user_profile: object(),
    )
    monkeypatch.setattr(
        evaluation,
        "score_strict_cfkg_candidates",
        lambda bundle, head_embedding, candidate_movie_ids: {"m1": 0.3, "m2": 0.8},
    )
    monkeypatch.setattr(
        evaluation,
        "fetch_movie_graph_profile_map",
        lambda driver, movie_ids, timeout_ms=None: {movie_id: {"genres": {"科幻"}} for movie_id in movie_ids},
    )
    monkeypatch.setattr(
        evaluation,
        "score_movie_against_user_profile",
        lambda movie_profile, user_profile: (0.0, [], []),
    )
    monkeypatch.setattr(
        evaluation,
        "load_reranker_bundle",
        lambda: {"path": "memory://reranker"},
    )
    monkeypatch.setattr(
        evaluation,
        "score_reranker_features",
        lambda bundle, feature_map: (
            feature_map["cfkg_score"] + 0.15 * feature_map["has_itemcf_source"],
            {
                "recall_score": 0.0,
                "recall_rank_score": 0.0,
                "source_count": 0.0,
                "has_cf_source": 0.0,
                "has_itemcf_source": 0.15 if feature_map["has_itemcf_source"] else 0.0,
                "has_content_source": 0.0,
                "has_ppr_source": 0.0,
                "cfkg_score": feature_map["cfkg_score"],
                "cfkg_rank_score": 0.0,
                "profile_score": 0.0,
                "genre_overlap_count": 0.0,
                "director_overlap_count": 0.0,
                "actor_overlap_count": 0.0,
                "negative_signal_count": 0.0,
                "negative_overlap_count": 0.0,
            },
        ),
    )

    ranked = asyncio.run(
        evaluation.get_strict_cfkg_recommendations(
            conn=object(),
            user_id=1,
            user_profile={"positive_features": {"genres": {"科幻": 1.0}}},
            seen_movie_ids=[],
            interaction_cutoff=None,
            limit=5,
            timeout_ms=800,
        )
    )

    assert [item["movie_id"] for item in ranked] == ["m2", "m1"]
    assert ranked[0]["score_breakdown"]["itemcf"] == 0.15
    assert "learned reranker" in ranked[0]["reasons"][1]
