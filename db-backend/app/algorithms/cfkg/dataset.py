"""
CFKG dataset export and loading utilities.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.algorithms.common import dedupe_preserve_order
from app.algorithms.cfkg.artifacts import (
    DEFAULT_DATASET_ROOT,
    ENTITY_TYPE_ORDER,
    RELATION_NAMES,
    ensure_dir,
    make_entity_key,
    natural_sort_key,
    relation_records,
    resolve_latest_dataset_dir,
    write_latest_pointer,
)
from app.db.neo4j import Neo4jConnection


@dataclass(frozen=True)
class EntityRecord:
    entity_id: int
    entity_key: str
    entity_type: str
    raw_id: str
    label: str


@dataclass
class ExportedCFKGDataset:
    dataset_dir: Path
    metadata: dict[str, Any]
    entities: list[EntityRecord]
    relations: list[dict[str, Any]]
    train_triples: list[tuple[int, int, int]]
    eval_triples: list[tuple[int, int, int]]
    holdout_cases: list[dict[str, Any]]

    entity_key_to_id: dict[str, int]
    entity_id_to_key: dict[int, str]
    entity_id_to_type: dict[int, str]
    entity_id_to_label: dict[int, str]
    relation_name_to_id: dict[str, int]
    relation_id_to_name: dict[int, str]
    entity_ids_by_type: dict[str, list[int]]
    movie_entity_ids: list[int]
    movie_entity_id_to_mid: dict[int, str]
    user_entity_to_user_id: dict[int, int]
    user_positive_items: dict[int, set[int]]
    user_negative_items: dict[int, set[int]]
    interaction_explicit_negative_pools: dict[tuple[int, int], list[int]]
    interaction_semantic_negative_pools: dict[tuple[int, int], list[int]]
    interaction_hard_negative_pools: dict[tuple[int, int], list[int]]


def _json_default(value: Any):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file_obj:
        for row in rows:
            file_obj.write(json.dumps(row, ensure_ascii=False, default=_json_default))
            file_obj.write("\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as file_obj:
        for line in file_obj:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _write_triples(path: Path, triples: Iterable[tuple[int, int, int]]) -> None:
    with path.open("w", encoding="utf-8") as file_obj:
        for head_id, relation_id, tail_id in triples:
            file_obj.write(f"{head_id}\t{relation_id}\t{tail_id}\n")


def _read_triples(path: Path) -> list[tuple[int, int, int]]:
    triples = []
    if not path.exists():
        return triples
    with path.open("r", encoding="utf-8") as file_obj:
        for line in file_obj:
            line = line.strip()
            if not line:
                continue
            head_id, relation_id, tail_id = line.split("\t")
            triples.append((int(head_id), int(relation_id), int(tail_id)))
    return triples


def _iter_chunks(items: Sequence[str], chunk_size: int = 1000) -> Iterable[list[str]]:
    for index in range(0, len(items), chunk_size):
        yield list(items[index:index + chunk_size])


def build_time_split_case(rows: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    holdout_index = None
    for index, row in enumerate(rows):
        if float(row["rating"]) >= 4.0:
            holdout_index = index

    if holdout_index is None or holdout_index == 0:
        return None

    history_rows = list(rows[:holdout_index])
    positive_seed_ids = dedupe_preserve_order(
        [row["mid"] for row in history_rows if float(row["rating"]) >= 4.0]
    )
    seed_movie_ids = list(reversed(positive_seed_ids[-5:]))
    if not seed_movie_ids:
        return None

    holdout_row = dict(rows[holdout_index])
    seen_movie_ids = dedupe_preserve_order([row["mid"] for row in history_rows])
    return {
        "holdout_row": holdout_row,
        "history_rows": history_rows,
        "seed_movie_ids": seed_movie_ids,
        "seen_movie_ids": seen_movie_ids,
    }


def _fetch_active_users(conn) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, username FROM users WHERE status = 'active' ORDER BY id ASC"
        )
        return cursor.fetchall()


def _fetch_rating_rows(conn) -> dict[int, list[dict[str, Any]]]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT r.user_id, r.mid, r.rating, r.rated_at, r.updated_at, r.id
            FROM user_movie_ratings AS r
            INNER JOIN users AS u ON u.id = r.user_id
            WHERE u.status = 'active'
            ORDER BY r.user_id ASC,
                     COALESCE(r.updated_at, r.rated_at) ASC,
                     r.rated_at ASC,
                     r.id ASC
            """
        )
        rows = cursor.fetchall()

    grouped = defaultdict(list)
    for row in rows:
        grouped[int(row["user_id"])].append({
            "user_id": int(row["user_id"]),
            "mid": str(row["mid"]),
            "rating": float(row["rating"]),
            "event_time": row.get("updated_at") or row.get("rated_at"),
        })
    return grouped


def _fetch_like_rows(conn) -> dict[int, list[dict[str, Any]]]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.user_id, p.mid, p.pref_type, p.created_at, p.updated_at
            FROM user_movie_prefs AS p
            INNER JOIN users AS u ON u.id = p.user_id
            WHERE u.status = 'active' AND p.pref_type = 'like'
            ORDER BY p.user_id ASC,
                     COALESCE(p.updated_at, p.created_at) ASC,
                     p.created_at ASC,
                     p.id ASC
            """
        )
        rows = cursor.fetchall()

    grouped = defaultdict(list)
    for row in rows:
        grouped[int(row["user_id"])].append({
            "user_id": int(row["user_id"]),
            "mid": str(row["mid"]),
            "event_time": row.get("updated_at") or row.get("created_at"),
        })
    return grouped


def _build_user_holdout_case(
    user_id: int,
    username: str,
    rating_rows: Sequence[dict[str, Any]],
    like_rows: Sequence[dict[str, Any]],
) -> dict[str, Any] | None:
    if not rating_rows and not like_rows:
        return None

    split_case = build_time_split_case(rating_rows)
    if split_case:
        history_rows = split_case["history_rows"]
        holdout_row = split_case["holdout_row"]
        split_time = holdout_row["event_time"]
    else:
        history_rows = list(rating_rows)
        holdout_row = None
        split_time = None

    positive_rating_ids = dedupe_preserve_order(
        [row["mid"] for row in history_rows if float(row["rating"]) >= 4.0]
    )
    negative_rating_ids = dedupe_preserve_order(
        [row["mid"] for row in history_rows if float(row["rating"]) <= 3.0]
    )
    like_ids = dedupe_preserve_order([
        row["mid"]
        for row in like_rows
        if split_time is None or row["event_time"] < split_time
    ])
    train_positive_movie_ids = dedupe_preserve_order(positive_rating_ids + like_ids)
    if not train_positive_movie_ids:
        return None

    return {
        "user_id": user_id,
        "username": username,
        "train_positive_movie_ids": train_positive_movie_ids,
        "negative_movie_ids": negative_rating_ids,
        "seed_movie_ids": split_case["seed_movie_ids"] if split_case else positive_rating_ids[-5:],
        "seen_movie_ids": split_case["seen_movie_ids"] if split_case else dedupe_preserve_order([row["mid"] for row in history_rows]),
        "holdout_movie_mid": holdout_row["mid"] if holdout_row else None,
        "split_time": split_time.isoformat() if split_time else None,
    }


def _fetch_movie_labels(conn, movie_ids: Sequence[str]) -> dict[str, str]:
    movie_labels: dict[str, str] = {}
    ids = list(dedupe_preserve_order(movie_ids))
    if not ids:
        return movie_labels

    with conn.cursor() as cursor:
        for chunk in _iter_chunks(ids):
            placeholders = ", ".join(["%s"] * len(chunk))
            cursor.execute(
                f"SELECT douban_id, name FROM movies WHERE douban_id IN ({placeholders})",
                chunk,
            )
            for row in cursor.fetchall():
                movie_labels[str(row["douban_id"])] = row.get("name") or str(row["douban_id"])
    return movie_labels


def _fetch_kg_rows(driver) -> dict[str, list[dict[str, Any]]]:
    queries = {
        "has_genre": """
            MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre)
            RETURN m.mid AS movie_mid,
                   coalesce(m.title, m.name, m.mid) AS movie_label,
                   g.name AS genre_name
            ORDER BY movie_mid ASC, genre_name ASC
        """,
        "directed_by": """
            MATCH (p:Person)-[:DIRECTED]->(m:Movie)
            RETURN m.mid AS movie_mid,
                   coalesce(m.title, m.name, m.mid) AS movie_label,
                   p.pid AS person_id,
                   coalesce(p.name_zh, p.name, p.pid) AS person_name
            ORDER BY movie_mid ASC, person_id ASC
        """,
        "acted_by": """
            MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
            RETURN m.mid AS movie_mid,
                   coalesce(m.title, m.name, m.mid) AS movie_label,
                   p.pid AS person_id,
                   coalesce(p.name_zh, p.name, p.pid) AS person_name
            ORDER BY movie_mid ASC, person_id ASC
        """,
    }
    rows = {}
    with driver.session() as session:
        for relation_name, query in queries.items():
            rows[relation_name] = [dict(record) for record in session.run(query)]
    return rows


def _build_movie_relation_index(kg_rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    movie_to_genres = defaultdict(set)
    movie_to_directors = defaultdict(set)
    movie_to_actors = defaultdict(set)
    genre_to_movies = defaultdict(set)
    director_to_movies = defaultdict(set)
    actor_to_movies = defaultdict(set)

    for row in kg_rows["has_genre"]:
        movie_mid = str(row["movie_mid"])
        genre_name = str(row["genre_name"])
        movie_to_genres[movie_mid].add(genre_name)
        genre_to_movies[genre_name].add(movie_mid)

    for row in kg_rows["directed_by"]:
        movie_mid = str(row["movie_mid"])
        person_id = str(row["person_id"])
        movie_to_directors[movie_mid].add(person_id)
        director_to_movies[person_id].add(movie_mid)

    for row in kg_rows["acted_by"]:
        movie_mid = str(row["movie_mid"])
        person_id = str(row["person_id"])
        movie_to_actors[movie_mid].add(person_id)
        actor_to_movies[person_id].add(movie_mid)

    return {
        "movie_to_genres": movie_to_genres,
        "movie_to_directors": movie_to_directors,
        "movie_to_actors": movie_to_actors,
        "genre_to_movies": genre_to_movies,
        "director_to_movies": director_to_movies,
        "actor_to_movies": actor_to_movies,
    }


def _semantic_negative_candidates_for_movie(
    positive_movie_mid: str,
    blocked_movie_ids: set[str],
    relation_index: dict[str, Any],
) -> list[str]:
    candidate_scores = defaultdict(float)

    for genre_name in relation_index["movie_to_genres"].get(positive_movie_mid, set()):
        for candidate_mid in relation_index["genre_to_movies"].get(genre_name, set()):
            if candidate_mid not in blocked_movie_ids:
                candidate_scores[candidate_mid] += 1.0

    for person_id in relation_index["movie_to_directors"].get(positive_movie_mid, set()):
        for candidate_mid in relation_index["director_to_movies"].get(person_id, set()):
            if candidate_mid not in blocked_movie_ids:
                candidate_scores[candidate_mid] += 2.5

    for person_id in relation_index["movie_to_actors"].get(positive_movie_mid, set()):
        for candidate_mid in relation_index["actor_to_movies"].get(person_id, set()):
            if candidate_mid not in blocked_movie_ids:
                candidate_scores[candidate_mid] += 0.8

    ranked = sorted(
        candidate_scores.items(),
        key=lambda item: (-item[1], natural_sort_key(item[0])),
    )
    return [movie_mid for movie_mid, _ in ranked]


def _build_entity_records(
    user_cases: Sequence[dict[str, Any]],
    movie_labels: dict[str, str],
    person_labels: dict[str, str],
    genre_labels: dict[str, str],
) -> list[EntityRecord]:
    raw_records = []

    for user_case in user_cases:
        raw_records.append({
            "entity_type": "User",
            "raw_id": str(user_case["user_id"]),
            "label": user_case["username"],
        })
    for movie_mid, label in movie_labels.items():
        raw_records.append({
            "entity_type": "Movie",
            "raw_id": str(movie_mid),
            "label": label or str(movie_mid),
        })
    for person_id, label in person_labels.items():
        raw_records.append({
            "entity_type": "Person",
            "raw_id": str(person_id),
            "label": label or str(person_id),
        })
    for genre_name, label in genre_labels.items():
        raw_records.append({
            "entity_type": "Genre",
            "raw_id": str(genre_name),
            "label": label or str(genre_name),
        })

    deduped = {}
    for item in raw_records:
        entity_key = make_entity_key(item["entity_type"], item["raw_id"])
        deduped[entity_key] = item

    sorted_records = sorted(
        deduped.values(),
        key=lambda item: (
            ENTITY_TYPE_ORDER[item["entity_type"]],
            natural_sort_key(item["raw_id"]),
        ),
    )
    return [
        EntityRecord(
            entity_id=index,
            entity_key=make_entity_key(item["entity_type"], item["raw_id"]),
            entity_type=item["entity_type"],
            raw_id=item["raw_id"],
            label=item["label"],
        )
        for index, item in enumerate(sorted_records)
    ]


def export_cfkg_dataset(
    conn,
    driver=None,
    dataset_root: str | Path = DEFAULT_DATASET_ROOT,
    version: str | None = None,
) -> dict[str, Any]:
    active_users = _fetch_active_users(conn)
    rating_rows_by_user = _fetch_rating_rows(conn)
    like_rows_by_user = _fetch_like_rows(conn)
    driver = driver or Neo4jConnection.get_driver()
    kg_rows = _fetch_kg_rows(driver)
    relation_index = _build_movie_relation_index(kg_rows)

    user_cases = []
    for user in active_users:
        user_case = _build_user_holdout_case(
            user_id=int(user["id"]),
            username=user["username"],
            rating_rows=rating_rows_by_user.get(int(user["id"]), []),
            like_rows=like_rows_by_user.get(int(user["id"]), []),
        )
        if user_case is not None:
            user_cases.append(user_case)

    movie_labels = {}
    person_labels = {}
    genre_labels = {}

    for row in kg_rows["has_genre"]:
        movie_labels[str(row["movie_mid"])] = row.get("movie_label") or str(row["movie_mid"])
        genre_labels[str(row["genre_name"])] = str(row["genre_name"])
    for row in kg_rows["directed_by"] + kg_rows["acted_by"]:
        movie_labels[str(row["movie_mid"])] = row.get("movie_label") or str(row["movie_mid"])
        person_labels[str(row["person_id"])] = row.get("person_name") or str(row["person_id"])

    interaction_movie_ids = dedupe_preserve_order([
        movie_id
        for user_case in user_cases
        for movie_id in (
            list(user_case["train_positive_movie_ids"])
            + list(user_case["negative_movie_ids"])
            + list(user_case["seen_movie_ids"])
            + ([user_case["holdout_movie_mid"]] if user_case["holdout_movie_mid"] else [])
        )
    ])
    missing_movie_ids = [movie_id for movie_id in interaction_movie_ids if movie_id not in movie_labels]
    movie_labels.update(_fetch_movie_labels(conn, missing_movie_ids))

    entities = _build_entity_records(
        user_cases=user_cases,
        movie_labels=movie_labels,
        person_labels=person_labels,
        genre_labels=genre_labels,
    )
    entity_key_to_id = {entity.entity_key: entity.entity_id for entity in entities}
    relation_name_to_id = {
        item["relation_name"]: int(item["relation_id"])
        for item in relation_records()
    }

    train_triples = set()
    eval_triples = set()
    holdout_rows = []
    interaction_negative_rows = []
    semantic_negative_cache = {
        positive_movie_mid: _semantic_negative_candidates_for_movie(
            positive_movie_mid=positive_movie_mid,
            blocked_movie_ids={positive_movie_mid},
            relation_index=relation_index,
        )
        for positive_movie_mid in {
            movie_id
            for user_case in user_cases
            for movie_id in user_case["train_positive_movie_ids"]
        }
    }

    for user_case in user_cases:
        user_entity_id = entity_key_to_id[make_entity_key("User", str(user_case["user_id"]))]
        positive_entity_ids = [
            entity_key_to_id[make_entity_key("Movie", movie_id)]
            for movie_id in user_case["train_positive_movie_ids"]
            if make_entity_key("Movie", movie_id) in entity_key_to_id
        ]
        negative_entity_ids = [
            entity_key_to_id[make_entity_key("Movie", movie_id)]
            for movie_id in user_case["negative_movie_ids"]
            if make_entity_key("Movie", movie_id) in entity_key_to_id
        ]
        for movie_entity_id in positive_entity_ids:
            train_triples.add((user_entity_id, relation_name_to_id["interact"], movie_entity_id))
            train_triples.add((movie_entity_id, relation_name_to_id["rev_interact"], user_entity_id))

        holdout_entity_id = None
        holdout_movie_mid = user_case["holdout_movie_mid"]
        if holdout_movie_mid and make_entity_key("Movie", holdout_movie_mid) in entity_key_to_id:
            holdout_entity_id = entity_key_to_id[make_entity_key("Movie", holdout_movie_mid)]
            eval_triples.add((user_entity_id, relation_name_to_id["interact"], holdout_entity_id))
            eval_triples.add((holdout_entity_id, relation_name_to_id["rev_interact"], user_entity_id))

        blocked_movie_ids = set(user_case["train_positive_movie_ids"])
        if holdout_movie_mid:
            blocked_movie_ids.add(holdout_movie_mid)

        holdout_rows.append({
            "user_id": user_case["user_id"],
            "username": user_case["username"],
            "user_entity_id": user_entity_id,
            "train_positive_movie_ids": list(user_case["train_positive_movie_ids"]),
            "train_positive_entity_ids": positive_entity_ids,
            "negative_movie_ids": list(user_case["negative_movie_ids"]),
            "negative_entity_ids": negative_entity_ids,
            "seed_movie_ids": list(user_case["seed_movie_ids"]),
            "seen_movie_ids": list(user_case["seen_movie_ids"]),
            "holdout_movie_mid": holdout_movie_mid,
            "holdout_entity_id": holdout_entity_id,
            "split_time": user_case["split_time"],
        })

        explicit_negative_ids = [
            entity_key_to_id[make_entity_key("Movie", movie_id)]
            for movie_id in user_case["negative_movie_ids"]
            if make_entity_key("Movie", movie_id) in entity_key_to_id
            and movie_id != holdout_movie_mid
        ]
        explicit_negative_ids = dedupe_preserve_order(explicit_negative_ids)

        for positive_movie_mid in user_case["train_positive_movie_ids"]:
            positive_movie_key = make_entity_key("Movie", positive_movie_mid)
            if positive_movie_key not in entity_key_to_id:
                continue

            semantic_negative_entity_ids = [
                entity_key_to_id[make_entity_key("Movie", movie_id)]
                for movie_id in semantic_negative_cache.get(positive_movie_mid, [])
                if movie_id not in blocked_movie_ids
                if make_entity_key("Movie", movie_id) in entity_key_to_id
            ]
            interaction_negative_rows.append({
                "user_entity_id": user_entity_id,
                "positive_movie_entity_id": entity_key_to_id[positive_movie_key],
                "explicit_negative_entity_ids": explicit_negative_ids,
                "semantic_negative_entity_ids": dedupe_preserve_order(semantic_negative_entity_ids),
                "negative_entity_ids": dedupe_preserve_order(
                    explicit_negative_ids + semantic_negative_entity_ids
                ),
            })

    for row in kg_rows["has_genre"]:
        movie_key = make_entity_key("Movie", str(row["movie_mid"]))
        genre_key = make_entity_key("Genre", str(row["genre_name"]))
        if movie_key in entity_key_to_id and genre_key in entity_key_to_id:
            train_triples.add((
                entity_key_to_id[movie_key],
                relation_name_to_id["has_genre"],
                entity_key_to_id[genre_key],
            ))
            train_triples.add((
                entity_key_to_id[genre_key],
                relation_name_to_id["genre_of"],
                entity_key_to_id[movie_key],
            ))
    for row, relation_name in (
        *((item, "directed_by") for item in kg_rows["directed_by"]),
        *((item, "acted_by") for item in kg_rows["acted_by"]),
    ):
        movie_key = make_entity_key("Movie", str(row["movie_mid"]))
        person_key = make_entity_key("Person", str(row["person_id"]))
        if movie_key in entity_key_to_id and person_key in entity_key_to_id:
            train_triples.add((
                entity_key_to_id[movie_key],
                relation_name_to_id[relation_name],
                entity_key_to_id[person_key],
            ))
            reverse_relation_name = "directs" if relation_name == "directed_by" else "acts_in"
            train_triples.add((
                entity_key_to_id[person_key],
                relation_name_to_id[reverse_relation_name],
                entity_key_to_id[movie_key],
            ))

    version = version or datetime.now().strftime("%Y%m%d-%H%M%S")
    dataset_root_path = Path(dataset_root)
    if not dataset_root_path.is_absolute():
        dataset_root_path = (Path(__file__).resolve().parents[3] / dataset_root_path).resolve()
    dataset_dir = ensure_dir(dataset_root_path / version)

    entity_rows = [
        {
            "entity_id": entity.entity_id,
            "entity_key": entity.entity_key,
            "entity_type": entity.entity_type,
            "raw_id": entity.raw_id,
            "label": entity.label,
        }
        for entity in entities
    ]
    relation_rows = relation_records()
    train_triples_sorted = sorted(train_triples)
    eval_triples_sorted = sorted(eval_triples)

    metadata = {
        "version": version,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "entity_count": len(entity_rows),
        "relation_count": len(relation_rows),
        "train_triple_count": len(train_triples_sorted),
        "eval_triple_count": len(eval_triples_sorted),
        "interaction_negative_pool_count": len(interaction_negative_rows),
        "holdout_user_count": sum(1 for row in holdout_rows if row["holdout_entity_id"] is not None),
        "selected_user_count": len(user_cases),
        "movie_count": sum(1 for entity in entities if entity.entity_type == "Movie"),
        "person_count": sum(1 for entity in entities if entity.entity_type == "Person"),
        "genre_count": sum(1 for entity in entities if entity.entity_type == "Genre"),
        "relation_names": list(RELATION_NAMES),
    }

    _write_jsonl(dataset_dir / "entities.jsonl", entity_rows)
    _write_jsonl(dataset_dir / "relations.jsonl", relation_rows)
    _write_triples(dataset_dir / "triples_train.tsv", train_triples_sorted)
    _write_triples(dataset_dir / "triples_eval.tsv", eval_triples_sorted)
    _write_jsonl(dataset_dir / "user_item_holdout.jsonl", holdout_rows)
    _write_jsonl(dataset_dir / "interaction_hard_negatives.jsonl", interaction_negative_rows)
    with (dataset_dir / "metadata.json").open("w", encoding="utf-8") as file_obj:
        json.dump(metadata, file_obj, ensure_ascii=False, indent=2)
    write_latest_pointer(dataset_root_path, version)

    return {
        "dataset_dir": str(dataset_dir),
        "metadata": metadata,
    }


def load_exported_dataset(dataset_dir: str | Path | None = None) -> ExportedCFKGDataset:
    resolved_dir = resolve_latest_dataset_dir(dataset_dir=dataset_dir)
    entity_rows = _read_jsonl(resolved_dir / "entities.jsonl")
    relation_rows = _read_jsonl(resolved_dir / "relations.jsonl")
    train_triples = _read_triples(resolved_dir / "triples_train.tsv")
    eval_triples = _read_triples(resolved_dir / "triples_eval.tsv")
    holdout_rows = _read_jsonl(resolved_dir / "user_item_holdout.jsonl")
    interaction_negative_rows = _read_jsonl(resolved_dir / "interaction_hard_negatives.jsonl")
    metadata = json.loads((resolved_dir / "metadata.json").read_text(encoding="utf-8"))

    entities = [
        EntityRecord(
            entity_id=int(row["entity_id"]),
            entity_key=row["entity_key"],
            entity_type=row["entity_type"],
            raw_id=str(row["raw_id"]),
            label=row["label"],
        )
        for row in entity_rows
    ]
    entity_key_to_id = {entity.entity_key: entity.entity_id for entity in entities}
    entity_id_to_key = {entity.entity_id: entity.entity_key for entity in entities}
    entity_id_to_type = {entity.entity_id: entity.entity_type for entity in entities}
    entity_id_to_label = {entity.entity_id: entity.label for entity in entities}
    relation_name_to_id = {
        row["relation_name"]: int(row["relation_id"])
        for row in relation_rows
    }
    relation_id_to_name = {
        int(row["relation_id"]): row["relation_name"]
        for row in relation_rows
    }
    entity_ids_by_type = defaultdict(list)
    for entity in entities:
        entity_ids_by_type[entity.entity_type].append(entity.entity_id)

    movie_entity_ids = list(entity_ids_by_type.get("Movie", []))
    movie_entity_id_to_mid = {
        entity.entity_id: entity.raw_id
        for entity in entities
        if entity.entity_type == "Movie"
    }
    user_entity_to_user_id = {
        entity.entity_id: int(entity.raw_id)
        for entity in entities
        if entity.entity_type == "User"
    }

    user_positive_items: dict[int, set[int]] = {}
    user_negative_items: dict[int, set[int]] = {}
    for row in holdout_rows:
        user_entity_id = int(row["user_entity_id"])
        user_positive_items[user_entity_id] = set(int(item) for item in row.get("train_positive_entity_ids", []))
        user_negative_items[user_entity_id] = set(int(item) for item in row.get("negative_entity_ids", []))
    interaction_explicit_negative_pools: dict[tuple[int, int], list[int]] = {}
    interaction_semantic_negative_pools: dict[tuple[int, int], list[int]] = {}
    interaction_hard_negative_pools: dict[tuple[int, int], list[int]] = {}
    for row in interaction_negative_rows:
        key = (int(row["user_entity_id"]), int(row["positive_movie_entity_id"]))
        interaction_explicit_negative_pools[key] = [
            int(item)
            for item in row.get("explicit_negative_entity_ids", [])
        ]
        interaction_semantic_negative_pools[key] = [
            int(item)
            for item in row.get("semantic_negative_entity_ids", [])
        ]
        interaction_hard_negative_pools[key] = [
            int(item)
            for item in row.get("negative_entity_ids", [])
        ]

    return ExportedCFKGDataset(
        dataset_dir=resolved_dir,
        metadata=metadata,
        entities=entities,
        relations=relation_rows,
        train_triples=train_triples,
        eval_triples=eval_triples,
        holdout_cases=holdout_rows,
        entity_key_to_id=entity_key_to_id,
        entity_id_to_key=entity_id_to_key,
        entity_id_to_type=entity_id_to_type,
        entity_id_to_label=entity_id_to_label,
        relation_name_to_id=relation_name_to_id,
        relation_id_to_name=relation_id_to_name,
        entity_ids_by_type=dict(entity_ids_by_type),
        movie_entity_ids=movie_entity_ids,
        movie_entity_id_to_mid=movie_entity_id_to_mid,
        user_entity_to_user_id=user_entity_to_user_id,
        user_positive_items=user_positive_items,
        user_negative_items=user_negative_items,
        interaction_explicit_negative_pools=interaction_explicit_negative_pools,
        interaction_semantic_negative_pools=interaction_semantic_negative_pools,
        interaction_hard_negative_pools=interaction_hard_negative_pools,
    )
