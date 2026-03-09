"""
纯内容 TF-IDF 基线推荐。
"""
from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
import math
import re
from threading import RLock
from typing import Any, Dict, List

import jieba

from app.algorithms.common import dedupe_preserve_order, split_multi_value

DEFAULT_TIMEOUT_MS = 2500
MOVIE_VECTOR_TERM_LIMIT = 24
USER_VECTOR_TERM_LIMIT = 80
STORYLINE_TOKEN_LIMIT = 36
TITLE_TOKEN_LIMIT = 10
EXPLAIN_SUPPORT_LIMIT = 3

_BUNDLE_LOCK = RLock()
_BUNDLE_CACHE: dict[str, Any] = {
    "bundle": None,
}

MOVIE_TEXT_QUERY = """
SELECT douban_id AS movie_id,
       name AS title,
       genres,
       regions,
       languages,
       directors,
       actors,
       storyline
FROM movies
WHERE type = 'movie'
  AND douban_id IS NOT NULL
"""

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]{2,}|[\u4e00-\u9fff]+")
STOPWORDS = {
    "电影",
    "影片",
    "故事",
    "一个",
    "一些",
    "他们",
    "她们",
    "自己",
    "没有",
    "可以",
    "以及",
    "如果",
    "因为",
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
}
STRUCTURED_TERM_PREFIXES = {
    "genre": "类型",
    "region": "地区",
    "lang": "语言",
    "director": "导演",
    "actor": "演员",
}


def _resolve_positive_context(
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
) -> tuple[List[str], Dict[str, float]]:
    if not user_profile:
        movie_ids = dedupe_preserve_order(seed_movie_ids)
        return movie_ids[:24], {movie_id: 1.0 for movie_id in movie_ids[:24]}

    movie_feedback = user_profile.get("movie_feedback", {})
    positive_movie_ids = dedupe_preserve_order(
        user_profile.get("context_movie_ids")
        or user_profile.get("positive_movie_ids")
        or [],
    )[:24]
    positive_weights = {
        movie_id: float(movie_feedback.get(movie_id, {}).get("positive_weight") or 1.0)
        for movie_id in positive_movie_ids
    }
    return positive_movie_ids, positive_weights


def _normalize_token(token: str) -> str | None:
    normalized = str(token or "").strip().lower()
    if not normalized or normalized in STOPWORDS:
        return None
    if len(normalized) <= 1 and not re.search(r"[\u4e00-\u9fff]", normalized):
        return None
    return normalized


def _tokenize_free_text(text: str | None, limit: int) -> List[str]:
    if not text:
        return []

    tokens: List[str] = []
    for chunk in TOKEN_PATTERN.findall(str(text)):
        if re.search(r"[\u4e00-\u9fff]", chunk):
            for token in jieba.lcut(chunk, cut_all=False):
                normalized = _normalize_token(token)
                if normalized:
                    tokens.append(normalized)
        else:
            normalized = _normalize_token(chunk)
            if normalized:
                tokens.append(normalized)
        if len(tokens) >= limit:
            break
    return tokens[:limit]


def _split_people(value: str | None) -> List[str]:
    return sorted(split_multi_value(value))


def _build_document_counter(row: Dict[str, Any]) -> Counter:
    counter: Counter = Counter()
    for token in _tokenize_free_text(row.get("title"), TITLE_TOKEN_LIMIT):
        counter[token] += 1.8
    for genre in split_multi_value(row.get("genres")):
        counter[f"genre:{genre}"] += 2.4
    for region in split_multi_value(row.get("regions")):
        counter[f"region:{region}"] += 1.4
    for language in split_multi_value(row.get("languages")):
        counter[f"lang:{language}"] += 1.3
    for director in _split_people(row.get("directors"))[:6]:
        counter[f"director:{director}"] += 2.0
    for actor in _split_people(row.get("actors"))[:10]:
        counter[f"actor:{actor}"] += 1.1
    for token in _tokenize_free_text(row.get("storyline"), STORYLINE_TOKEN_LIMIT):
        counter[token] += 0.8
    return Counter({term: value for term, value in counter.items() if value > 0})


def _build_tfidf_bundle(conn) -> Dict[str, Any]:
    with conn.cursor() as cursor:
        cursor.execute(MOVIE_TEXT_QUERY)
        rows = cursor.fetchall()

    doc_count = len(rows)
    raw_counters: Dict[str, Counter] = {}
    document_frequency: Counter = Counter()
    title_map: Dict[str, str] = {}

    for row in rows:
        movie_id = str(row["movie_id"])
        title_map[movie_id] = row.get("title") or movie_id
        counter = _build_document_counter(row)
        if not counter:
            continue
        raw_counters[movie_id] = counter
        document_frequency.update(counter.keys())

    movie_vectors: Dict[str, Dict[str, float]] = {}
    postings: Dict[str, List[tuple[str, float]]] = defaultdict(list)
    for movie_id, counter in raw_counters.items():
        weighted_terms = {}
        for term, freq in counter.items():
            idf = math.log((1.0 + doc_count) / (1.0 + document_frequency[term])) + 1.0
            tf = 1.0 + math.log(float(freq))
            weighted_terms[term] = tf * idf
        top_terms = sorted(
            weighted_terms.items(),
            key=lambda item: (-item[1], item[0]),
        )[:MOVIE_VECTOR_TERM_LIMIT]
        norm = math.sqrt(sum(weight * weight for _, weight in top_terms)) or 1.0
        normalized_vector = {
            term: weight / norm
            for term, weight in top_terms
            if weight > 0
        }
        if not normalized_vector:
            continue
        movie_vectors[movie_id] = normalized_vector
        for term, weight in normalized_vector.items():
            postings[term].append((movie_id, weight))

    return {
        "movie_vectors": movie_vectors,
        "postings": dict(postings),
        "title_map": title_map,
        "doc_count": doc_count,
    }


def _get_or_build_bundle(conn) -> Dict[str, Any]:
    with _BUNDLE_LOCK:
        bundle = _BUNDLE_CACHE.get("bundle")
    if bundle is not None:
        return bundle

    bundle = _build_tfidf_bundle(conn)
    with _BUNDLE_LOCK:
        _BUNDLE_CACHE["bundle"] = bundle
    return bundle


def _normalize_vector(weight_map: Dict[str, float], limit: int | None = None) -> Dict[str, float]:
    if not weight_map:
        return {}
    ordered = sorted(
        weight_map.items(),
        key=lambda item: (-item[1], item[0]),
    )
    if limit is not None:
        ordered = ordered[:limit]
    norm = math.sqrt(sum(weight * weight for _, weight in ordered)) or 1.0
    return {term: weight / norm for term, weight in ordered if weight > 0}


def _build_user_vector(
    bundle: Dict[str, Any],
    positive_movie_ids: List[str],
    positive_weights: Dict[str, float],
) -> Dict[str, float]:
    user_terms: Counter = Counter()
    for movie_id in positive_movie_ids:
        movie_vector = bundle["movie_vectors"].get(movie_id)
        seed_weight = max(float(positive_weights.get(movie_id) or 0.0), 0.0)
        if not movie_vector or seed_weight <= 0:
            continue
        for term, weight in movie_vector.items():
            user_terms[term] += seed_weight * weight
    return _normalize_vector(dict(user_terms), limit=USER_VECTOR_TERM_LIMIT)


def _display_term(term: str) -> str:
    prefix, _, value = term.partition(":")
    if not value:
        return term
    label = STRUCTURED_TERM_PREFIXES.get(prefix)
    if not label:
        return value
    return f"{label}:{value}"


def _shared_term_labels(
    contribution_map: Dict[str, float],
    limit: int = 4,
) -> List[str]:
    return [
        _display_term(term)
        for term, _ in sorted(
            contribution_map.items(),
            key=lambda item: (-item[1], item[0]),
        )[:limit]
    ]


def _score_candidates(
    bundle: Dict[str, Any],
    user_vector: Dict[str, float],
    seen_movie_ids: List[str] | None = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    if not user_vector:
        return []

    seen_set = set(dedupe_preserve_order(seen_movie_ids))
    candidate_scores: Dict[str, float] = defaultdict(float)
    term_contributions: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for term, user_weight in user_vector.items():
        for movie_id, movie_weight in bundle["postings"].get(term, []):
            if movie_id in seen_set:
                continue
            contribution = user_weight * movie_weight
            if contribution <= 0:
                continue
            candidate_scores[movie_id] += contribution
            term_contributions[movie_id][term] += contribution

    if not candidate_scores:
        return []

    ranked = sorted(
        candidate_scores.items(),
        key=lambda item: (-item[1], item[0]),
    )[:limit]
    return [
        {
            "movie_id": movie_id,
            "score": float(score),
            "matched_terms": _shared_term_labels(term_contributions[movie_id]),
            "term_contributions": dict(term_contributions[movie_id]),
        }
        for movie_id, score in ranked
    ]


def _find_support_movies(
    bundle: Dict[str, Any],
    positive_movie_ids: List[str],
    positive_weights: Dict[str, float],
    candidate_movie_id: str,
    limit: int = EXPLAIN_SUPPORT_LIMIT,
) -> List[Dict[str, Any]]:
    candidate_vector = bundle["movie_vectors"].get(candidate_movie_id)
    if not candidate_vector:
        return []

    support_rows = []
    for movie_id in positive_movie_ids:
        movie_vector = bundle["movie_vectors"].get(movie_id)
        seed_weight = max(float(positive_weights.get(movie_id) or 0.0), 0.0)
        if not movie_vector or seed_weight <= 0:
            continue
        shared_terms = {}
        raw_similarity = 0.0
        for term, weight in candidate_vector.items():
            if term not in movie_vector:
                continue
            contribution = seed_weight * weight * movie_vector[term]
            if contribution <= 0:
                continue
            raw_similarity += contribution
            shared_terms[term] = contribution
        if raw_similarity <= 0:
            continue
        support_rows.append({
            "movie_id": movie_id,
            "title": bundle["title_map"].get(movie_id, movie_id),
            "similarity": raw_similarity,
            "matched_terms": _shared_term_labels(shared_terms),
            "term_contributions": shared_terms,
        })

    support_rows.sort(key=lambda item: (-float(item["similarity"]), item["movie_id"]))
    return support_rows[:limit]


def _format_tfidf_reasons(
    matched_terms: List[str],
    support_movies: List[Dict[str, Any]],
) -> List[str]:
    reasons = []
    if matched_terms:
        reasons.append("命中文本/内容特征 " + " / ".join(matched_terms[:3]))
    if support_movies:
        reasons.append(
            "与《" + "》《".join(item["title"] for item in support_movies[:2]) + "》的内容表征接近"
        )
    return reasons[:3] or ["与历史偏好电影的文本内容表征接近"]


def _get_tfidf_recommendations_sync(
    conn,
    user_id: int,
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    del user_id, timeout_ms
    positive_movie_ids, positive_weights = _resolve_positive_context(
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
    )
    if not positive_movie_ids:
        return []

    bundle = _get_or_build_bundle(conn)
    user_vector = _build_user_vector(
        bundle=bundle,
        positive_movie_ids=positive_movie_ids,
        positive_weights=positive_weights,
    )
    if not user_vector:
        return []

    candidate_limit = min(max(limit * 6, 120), 220)
    candidates = _score_candidates(
        bundle=bundle,
        user_vector=user_vector,
        seen_movie_ids=seen_movie_ids,
        limit=candidate_limit,
    )
    if not candidates:
        return []

    ranked_items = []
    for candidate in candidates[:limit]:
        support_movies = _find_support_movies(
            bundle=bundle,
            positive_movie_ids=positive_movie_ids,
            positive_weights=positive_weights,
            candidate_movie_id=candidate["movie_id"],
        )
        ranked_items.append({
            "movie_id": candidate["movie_id"],
            "score": float(candidate["score"]),
            "reasons": _format_tfidf_reasons(
                candidate.get("matched_terms") or [],
                support_movies,
            ),
            "negative_signals": [],
            "matched_terms": candidate.get("matched_terms") or [],
            "support_movies": support_movies,
            "source": "tfidf",
        })
    ranked_items.sort(key=lambda item: (-float(item["score"]), item["movie_id"]))
    return ranked_items[:limit]


def build_tfidf_explain_signals(
    conn,
    user_profile: Dict[str, Any] | None,
    target_mid: str,
    seed_movie_ids: List[str] | None = None,
) -> Dict[str, Any]:
    positive_movie_ids, positive_weights = _resolve_positive_context(
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
    )
    if not positive_movie_ids:
        return {"support_movies": [], "matched_terms": []}

    bundle = _get_or_build_bundle(conn)
    user_vector = _build_user_vector(
        bundle=bundle,
        positive_movie_ids=positive_movie_ids,
        positive_weights=positive_weights,
    )
    candidate_vector = bundle["movie_vectors"].get(str(target_mid))
    if not user_vector or not candidate_vector:
        return {"support_movies": [], "matched_terms": []}

    matched_terms = _shared_term_labels(
        {
            term: user_vector[term] * candidate_vector[term]
            for term in candidate_vector
            if term in user_vector
        },
    )
    support_movies = _find_support_movies(
        bundle=bundle,
        positive_movie_ids=positive_movie_ids,
        positive_weights=positive_weights,
        candidate_movie_id=str(target_mid),
    )
    return {
        "support_movies": support_movies,
        "matched_terms": matched_terms,
    }


async def get_tfidf_recommendations(
    conn,
    user_id: int,
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(
        _get_tfidf_recommendations_sync,
        conn,
        user_id,
        user_profile,
        seed_movie_ids,
        seen_movie_ids,
        limit,
        timeout_ms,
    )
