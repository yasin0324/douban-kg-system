"""
推荐算法公共工具
"""
from collections import Counter


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
        except TypeError:
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
