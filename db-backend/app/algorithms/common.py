"""
推荐算法公共工具
"""
from collections import Counter
from typing import Any, Dict, Iterable, List


def split_multi_value(value: str | None):
    if not value:
        return set()

    normalized = (
        str(value)
        .replace(" / ", "/")
        .replace("/ ", "/")
        .replace("、", "/")
        .replace(",", "/")
        .replace("，", "/")
    )
    return {part.strip() for part in normalized.split("/") if part.strip()}


def dedupe_preserve_order(values):
    if not values:
        return []

    seen = set()
    items = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        items.append(value)
    return items


def run_query(session, query: str, timeout_ms: int | None = None, **params):
    if timeout_ms:
        timeout_seconds = max(timeout_ms, 100) / 1000
        try:
            with session.begin_transaction(timeout=timeout_seconds) as tx:
                return list(tx.run(query, **params))
        except (TypeError, AttributeError):
            pass
    return list(session.run(query, **params))


def fetch_movie_feature_map(driver, movie_ids, timeout_ms: int | None = None):
    movie_ids = dedupe_preserve_order(movie_ids)
    if not movie_ids:
        return {}

    query = """
    MATCH (m:Movie)
    WHERE m.mid IN $movie_ids
    RETURN m.mid AS movie_id,
           m.regions AS regions,
           m.languages AS languages,
           m.year AS year,
           m.rating AS rating,
           m.content_type AS content_type,
           m.votes AS votes
    """

    with driver.session() as session:
        records = run_query(session, query, timeout_ms=timeout_ms, movie_ids=movie_ids)

    feature_map = {}
    for record in records:
        feature_map[record["movie_id"]] = {
            "regions": split_multi_value(record.get("regions")),
            "languages": split_multi_value(record.get("languages")),
            "year": int(record["year"]) if record.get("year") is not None else None,
            "rating": float(record["rating"]) if record.get("rating") is not None else None,
            "content_type": record.get("content_type"),
            "votes": int(record["votes"]) if record.get("votes") is not None else None,
        }
    return feature_map


def fetch_movie_graph_profile_map(driver, movie_ids, timeout_ms: int | None = None):
    movie_ids = dedupe_preserve_order(movie_ids)
    if not movie_ids:
        return {}

    query = """
    MATCH (m:Movie)
    WHERE m.mid IN $movie_ids
    OPTIONAL MATCH (m)-[:HAS_GENRE]->(g:Genre)
    WITH m, collect(DISTINCT g.name) AS genres
    OPTIONAL MATCH (m)<-[:DIRECTED]-(d:Person)
    WITH m, genres, collect(DISTINCT {pid: d.pid, name: d.name}) AS directors
    OPTIONAL MATCH (m)<-[:ACTED_IN]-(a:Person)
    RETURN m.mid AS movie_id,
           m.regions AS regions,
           m.languages AS languages,
           m.year AS year,
           m.rating AS rating,
           m.content_type AS content_type,
           m.votes AS votes,
           genres,
           directors,
           collect(DISTINCT {pid: a.pid, name: a.name})[..12] AS actors
    """

    with driver.session() as session:
        records = run_query(
            session,
            query,
            timeout_ms=timeout_ms,
            movie_ids=movie_ids,
        )

    profile_map: Dict[str, Dict[str, Any]] = {}
    for record in records:
        directors = [
            item for item in (record.get("directors") or []) if item.get("pid")
        ]
        actors = [item for item in (record.get("actors") or []) if item.get("pid")]
        profile_map[record["movie_id"]] = {
            "regions": split_multi_value(record.get("regions")),
            "languages": split_multi_value(record.get("languages")),
            "year": int(record["year"]) if record.get("year") is not None else None,
            "rating": float(record["rating"]) if record.get("rating") is not None else None,
            "content_type": record.get("content_type"),
            "votes": int(record["votes"]) if record.get("votes") is not None else None,
            "genres": {genre for genre in (record.get("genres") or []) if genre},
            "genre_names": [genre for genre in (record.get("genres") or []) if genre],
            "directors": directors,
            "director_ids": {item["pid"] for item in directors if item.get("pid")},
            "director_names": [item["name"] for item in directors if item.get("name")],
            "actors": actors,
            "actor_ids": {item["pid"] for item in actors if item.get("pid")},
            "actor_names": [item["name"] for item in actors if item.get("name")],
        }
    return profile_map


def build_seed_profile(feature_map, seed_ids):
    region_counter = Counter()
    language_counter = Counter()
    years = []
    ratings = []
    content_type_counter = Counter()

    for seed_id in seed_ids:
        features = feature_map.get(seed_id)
        if not features:
            continue
        region_counter.update(features["regions"])
        language_counter.update(features["languages"])
        if features["year"] is not None:
            years.append(features["year"])
        if features["rating"] is not None:
            ratings.append(features["rating"])
        if features["content_type"]:
            content_type_counter.update([features["content_type"]])

    return {
        "regions": region_counter,
        "languages": language_counter,
        "years": years,
        "ratings": ratings,
        "content_type_counter": content_type_counter,
    }


def build_weighted_user_profile(
    movie_profile_map: Dict[str, Dict[str, Any]],
    movie_feedback_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    positive_features = {
        "genres": Counter(),
        "directors": Counter(),
        "actors": Counter(),
        "regions": Counter(),
        "languages": Counter(),
    }
    negative_features = {
        "genres": Counter(),
        "directors": Counter(),
        "actors": Counter(),
        "regions": Counter(),
        "languages": Counter(),
    }
    exploration_features = {
        "genres": Counter(),
        "directors": Counter(),
        "actors": Counter(),
    }
    feature_labels = {
        "directors": {},
        "actors": {},
    }
    positive_years = []
    positive_ratings = []
    content_type_counter = Counter()

    for movie_id, feedback in movie_feedback_map.items():
        movie_profile = movie_profile_map.get(movie_id)
        if not movie_profile:
            continue

        positive_weight = float(feedback.get("positive_weight") or 0.0)
        negative_weight = float(feedback.get("negative_weight") or 0.0)
        exploration_weight = float(feedback.get("exploration_weight") or 0.0)

        if positive_weight > 0:
            positive_features["genres"].update(
                {genre: positive_weight for genre in movie_profile.get("genres", set())}
            )
            positive_features["regions"].update(
                {region: positive_weight for region in movie_profile.get("regions", set())}
            )
            positive_features["languages"].update(
                {language: positive_weight for language in movie_profile.get("languages", set())}
            )
            for director in movie_profile.get("directors", []):
                director_id = director.get("pid")
                if not director_id:
                    continue
                positive_features["directors"][director_id] += positive_weight
                feature_labels["directors"][director_id] = director.get("name") or director_id
            for actor in movie_profile.get("actors", []):
                actor_id = actor.get("pid")
                if not actor_id:
                    continue
                positive_features["actors"][actor_id] += positive_weight
                feature_labels["actors"][actor_id] = actor.get("name") or actor_id
            if movie_profile.get("year") is not None:
                repeat_count = max(1, int(round(positive_weight)))
                positive_years.extend([movie_profile["year"]] * repeat_count)
            if movie_profile.get("rating") is not None:
                repeat_count = max(1, int(round(positive_weight)))
                positive_ratings.extend([movie_profile["rating"]] * repeat_count)
            if movie_profile.get("content_type"):
                content_type_counter[movie_profile["content_type"]] += positive_weight

        if negative_weight > 0:
            negative_features["genres"].update(
                {genre: negative_weight for genre in movie_profile.get("genres", set())}
            )
            negative_features["regions"].update(
                {region: negative_weight for region in movie_profile.get("regions", set())}
            )
            negative_features["languages"].update(
                {language: negative_weight for language in movie_profile.get("languages", set())}
            )
            for director in movie_profile.get("directors", []):
                director_id = director.get("pid")
                if director_id:
                    negative_features["directors"][director_id] += negative_weight
            for actor in movie_profile.get("actors", []):
                actor_id = actor.get("pid")
                if actor_id:
                    negative_features["actors"][actor_id] += negative_weight

        if exploration_weight > 0:
            exploration_features["genres"].update(
                {genre: exploration_weight for genre in movie_profile.get("genres", set())}
            )
            for director in movie_profile.get("directors", []):
                director_id = director.get("pid")
                if director_id:
                    exploration_features["directors"][director_id] += exploration_weight
            for actor in movie_profile.get("actors", []):
                actor_id = actor.get("pid")
                if actor_id:
                    exploration_features["actors"][actor_id] += exploration_weight

    return {
        "positive_features": positive_features,
        "negative_features": negative_features,
        "exploration_features": exploration_features,
        "positive_years": positive_years,
        "positive_ratings": positive_ratings,
        "content_type_counter": content_type_counter,
        "feature_labels": feature_labels,
    }


def top_weighted_items(weight_map: Dict[str, float], limit: int) -> List[str]:
    if not weight_map:
        return []
    return [
        key
        for key, _ in sorted(
            weight_map.items(),
            key=lambda item: (-item[1], item[0]),
        )[:limit]
    ]


def score_movie_against_user_profile(
    candidate_features: Dict[str, Any] | None,
    profile: Dict[str, Any] | None,
) -> tuple[float, List[str], List[str]]:
    if not candidate_features or not profile:
        return 0.0, [], []

    positive_features = profile.get("positive_features", {})
    negative_features = profile.get("negative_features", {})
    exploration_features = profile.get("exploration_features", {})

    score = 0.0
    positive_reasons: List[str] = []
    negative_signals: List[str] = []

    def _sorted_overlap(values: Iterable[str], weight_map: Dict[str, float]):
        return sorted(
            [(value, weight_map[value]) for value in values if value in weight_map],
            key=lambda item: (-item[1], item[0]),
        )

    genre_overlap = _sorted_overlap(
        candidate_features.get("genres", set()),
        positive_features.get("genres", {}),
    )
    if genre_overlap:
        score += min(2.2, sum(weight for _, weight in genre_overlap[:3]) * 0.28)
        positive_reasons.append(
            f"偏好类型 {' / '.join(name for name, _ in genre_overlap[:2])}"
        )

    director_overlap = _sorted_overlap(
        candidate_features.get("director_ids", set()),
        positive_features.get("directors", {}),
    )
    if director_overlap:
        score += min(
            2.6,
            sum(weight for _, weight in director_overlap[:2]) * 0.34,
        )
        positive_reasons.append(
            f"偏好导演 {' / '.join(candidate_features.get('director_names', [])[:2])}"
        )

    actor_overlap = _sorted_overlap(
        candidate_features.get("actor_ids", set()),
        positive_features.get("actors", {}),
    )
    if actor_overlap:
        score += min(1.8, sum(weight for _, weight in actor_overlap[:3]) * 0.18)
        positive_reasons.append(
            f"偏好演员 {' / '.join(candidate_features.get('actor_names', [])[:2])}"
        )

    region_overlap = _sorted_overlap(
        candidate_features.get("regions", set()),
        positive_features.get("regions", {}),
    )
    if region_overlap:
        score += min(0.65, sum(weight for _, weight in region_overlap[:2]) * 0.08)
        positive_reasons.append(
            f"地区偏好 {' / '.join(name for name, _ in region_overlap[:2])}"
        )

    language_overlap = _sorted_overlap(
        candidate_features.get("languages", set()),
        positive_features.get("languages", {}),
    )
    if language_overlap:
        score += min(
            0.55,
            sum(weight for _, weight in language_overlap[:2]) * 0.06,
        )

    exploration_genres = _sorted_overlap(
        candidate_features.get("genres", set()),
        exploration_features.get("genres", {}),
    )
    if exploration_genres and not genre_overlap:
        score += min(
            0.35,
            sum(weight for _, weight in exploration_genres[:2]) * 0.08,
        )
        positive_reasons.append(
            f"延展想看兴趣 {' / '.join(name for name, _ in exploration_genres[:2])}"
        )

    negative_genres = _sorted_overlap(
        candidate_features.get("genres", set()),
        negative_features.get("genres", {}),
    )
    if negative_genres:
        penalty = min(0.9, sum(weight for _, weight in negative_genres[:2]) * 0.12)
        score -= penalty
        negative_signals.append(
            f"包含较弱负反馈类型 {' / '.join(name for name, _ in negative_genres[:2])}"
        )

    negative_directors = _sorted_overlap(
        candidate_features.get("director_ids", set()),
        negative_features.get("directors", {}),
    )
    if negative_directors:
        penalty = min(
            0.8,
            sum(weight for _, weight in negative_directors[:2]) * 0.14,
        )
        score -= penalty
        if candidate_features.get("director_names"):
            negative_signals.append(
                f"命中弱负反馈导演 {' / '.join(candidate_features['director_names'][:2])}"
            )

    negative_actors = _sorted_overlap(
        candidate_features.get("actor_ids", set()),
        negative_features.get("actors", {}),
    )
    if negative_actors:
        score -= min(
            0.65,
            sum(weight for _, weight in negative_actors[:3]) * 0.08,
        )

    metadata_bonus, metadata_reasons = score_metadata_alignment(
        candidate_features,
        {
            "regions": Counter(positive_features.get("regions", {})),
            "languages": Counter(positive_features.get("languages", {})),
            "years": profile.get("positive_years", []),
            "ratings": profile.get("positive_ratings", []),
            "content_type_counter": Counter(profile.get("content_type_counter", {})),
        },
    )
    score += metadata_bonus * 0.5
    for reason in metadata_reasons[:1]:
        positive_reasons.append(reason)

    deduped_reasons = []
    seen_reasons = set()
    for reason in positive_reasons:
        if reason in seen_reasons:
            continue
        seen_reasons.add(reason)
        deduped_reasons.append(reason)

    deduped_negative = []
    seen_negative = set()
    for signal in negative_signals:
        if signal in seen_negative:
            continue
        seen_negative.add(signal)
        deduped_negative.append(signal)

    return score, deduped_reasons[:3], deduped_negative[:2]


def score_metadata_alignment(candidate_features, seed_profile):
    if not candidate_features:
        return 0.0, []

    bonus = 0.0
    reasons = []

    region_overlap = candidate_features["regions"] & set(seed_profile["regions"].keys())
    if region_overlap:
        bonus += min(1.0, 0.35 * len(region_overlap))
        reasons.append(f"地区接近 {' / '.join(sorted(region_overlap)[:2])}")

    language_overlap = candidate_features["languages"] & set(seed_profile["languages"].keys())
    if language_overlap:
        bonus += min(0.8, 0.25 * len(language_overlap))
        reasons.append(f"语言接近 {' / '.join(sorted(language_overlap)[:2])}")

    if candidate_features["year"] is not None and seed_profile["years"]:
        year_gap = min(abs(candidate_features["year"] - year) for year in seed_profile["years"])
        if year_gap <= 2:
            bonus += 0.6
            reasons.append("年代接近")
        elif year_gap <= 5:
            bonus += 0.35
        elif year_gap <= 10:
            bonus += 0.15

    if candidate_features["rating"] is not None and seed_profile["ratings"]:
        avg_seed_rating = sum(seed_profile["ratings"]) / len(seed_profile["ratings"])
        if candidate_features["rating"] >= avg_seed_rating - 0.3:
            bonus += 0.25
        elif candidate_features["rating"] >= avg_seed_rating - 0.8:
            bonus += 0.08
        else:
            bonus -= 0.12

    if candidate_features["content_type"] and candidate_features["content_type"] in seed_profile["content_type_counter"]:
        bonus += 0.1

    if candidate_features["votes"] is not None:
        if candidate_features["votes"] >= 10000:
            bonus += 0.08
        elif candidate_features["votes"] < 100 and candidate_features["rating"] is None:
            bonus -= 0.05

    return bonus, reasons[:2]
