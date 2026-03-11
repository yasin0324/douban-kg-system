"""
Shared graph metadata cache for recommendation algorithms.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock

from app.db.mysql import get_connection
from app.db.neo4j import Neo4jConnection

REL_DIRECTOR = "director"
REL_ACTOR = "actor"
REL_GENRE = "genre"
REL_REGION = "region"
REL_LANGUAGE = "language"
REL_CONTENT_TYPE = "content_type"
REL_YEAR_BUCKET = "year_bucket"

CORE_RELATIONS = {REL_DIRECTOR, REL_ACTOR, REL_GENRE}
EXPANDED_RELATIONS = {
    REL_DIRECTOR,
    REL_ACTOR,
    REL_GENRE,
    REL_REGION,
    REL_LANGUAGE,
    REL_CONTENT_TYPE,
    REL_YEAR_BUCKET,
}

RELATION_TO_NODE_PREFIX = {
    REL_DIRECTOR: "person",
    REL_ACTOR: "person",
    REL_GENRE: "genre",
    REL_REGION: "region",
    REL_LANGUAGE: "language",
    REL_CONTENT_TYPE: "content_type",
    REL_YEAR_BUCKET: "year_bucket",
}

RELATION_TO_EMBED_EDGE = {
    REL_DIRECTOR: "DIRECTED",
    REL_ACTOR: "ACTED_IN",
    REL_GENRE: "HAS_GENRE",
    REL_REGION: "IN_REGION",
    REL_LANGUAGE: "IN_LANGUAGE",
    REL_CONTENT_TYPE: "HAS_CONTENT_TYPE",
    REL_YEAR_BUCKET: "IN_YEAR_BUCKET",
}

EMBED_EDGE_DIRECTIONS = {
    REL_DIRECTOR: ("person", "movie"),
    REL_ACTOR: ("person", "movie"),
    REL_GENRE: ("movie", "genre"),
    REL_REGION: ("movie", "region"),
    REL_LANGUAGE: ("movie", "language"),
    REL_CONTENT_TYPE: ("movie", "content_type"),
    REL_YEAR_BUCKET: ("movie", "year_bucket"),
}


def parse_slash_tokens(raw: str | None) -> set[str]:
    return {item.strip() for item in str(raw or "").split("/") if item.strip()}


def build_year_bucket(year: int | None) -> str | None:
    if not year:
        return None
    if year < 1990:
        return "before_1990"
    if year < 2000:
        return "1990s"
    if year < 2010:
        return "2000s"
    if year < 2020:
        return "2010s"
    return "2020s_plus"


def relation_token(relation: str, entity_id: str) -> str:
    return f"{relation}:{entity_id}"


def embed_entity_key(prefix: str, entity_id: str) -> str:
    return f"{prefix}_{entity_id}"


def inverse_relation_name(rel_name: str) -> str:
    return f"{rel_name}_REV"


def safe_idf(degree: int) -> float:
    return 1.0 / math.log(2.0 + max(degree, 1))


@dataclass(slots=True)
class MovieGraphProfile:
    mid: str
    name: str
    year: int | None = None
    content_type: str | None = None
    genres: set[str] = field(default_factory=set)
    regions: set[str] = field(default_factory=set)
    languages: set[str] = field(default_factory=set)
    year_bucket: str | None = None
    directors: set[str] = field(default_factory=set)
    actors: set[str] = field(default_factory=set)
    top_actors: set[str] = field(default_factory=set)
    actor_orders: dict[str, int] = field(default_factory=dict)

    def relation_entities(self, relation: str, *, actor_top_only: bool = False) -> set[str]:
        if relation == REL_DIRECTOR:
            return set(self.directors)
        if relation == REL_ACTOR:
            return set(self.top_actors if actor_top_only else self.actors)
        if relation == REL_GENRE:
            return set(self.genres)
        if relation == REL_REGION:
            return set(self.regions)
        if relation == REL_LANGUAGE:
            return set(self.languages)
        if relation == REL_CONTENT_TYPE:
            return {self.content_type} if self.content_type else set()
        if relation == REL_YEAR_BUCKET:
            return {self.year_bucket} if self.year_bucket else set()
        return set()

    def actor_ids(self, order_limit: int | None = None) -> set[str]:
        if order_limit is None:
            return set(self.actors)
        return {
            pid
            for pid, order in self.actor_orders.items()
            if int(order) <= int(order_limit)
        }


class GraphMetadataCache:
    _lock = Lock()
    _loaded = False
    _movie_profiles: dict[str, MovieGraphProfile] = {}
    _movie_mids: list[str] = []
    _movie_name_map: dict[str, str] = {}
    _person_name_map: dict[str, str] = {}
    _relation_inverted_index: dict[str, dict[str, set[str]]] = {}
    _relation_degrees: dict[str, dict[str, int]] = {}
    _triples_cache: dict[tuple[bool, bool], tuple[list[tuple[str, str, str]], set[str], dict[str, str], dict[str, tuple[str, str]]]] = {}

    @classmethod
    def clear(cls):
        with cls._lock:
            cls._loaded = False
            cls._movie_profiles = {}
            cls._movie_mids = []
            cls._movie_name_map = {}
            cls._person_name_map = {}
            cls._relation_inverted_index = {}
            cls._relation_degrees = {}
            cls._triples_cache = {}

    @classmethod
    def ensure_loaded(cls):
        if cls._loaded:
            return
        with cls._lock:
            if cls._loaded:
                return
            cls._load()
            cls._loaded = True

    @classmethod
    def movie_profiles(cls) -> dict[str, MovieGraphProfile]:
        cls.ensure_loaded()
        return cls._movie_profiles

    @classmethod
    def movie_mids(cls) -> list[str]:
        cls.ensure_loaded()
        return cls._movie_mids

    @classmethod
    def movie_name_map(cls) -> dict[str, str]:
        cls.ensure_loaded()
        return cls._movie_name_map

    @classmethod
    def person_name(cls, pid: str) -> str:
        cls.ensure_loaded()
        return cls._person_name_map.get(pid, pid)

    @classmethod
    def inverted_index(cls, relation: str) -> dict[str, set[str]]:
        cls.ensure_loaded()
        return cls._relation_inverted_index.get(relation, {})

    @classmethod
    def entity_degree(cls, relation: str, entity_id: str) -> int:
        cls.ensure_loaded()
        return cls._relation_degrees.get(relation, {}).get(entity_id, 0)

    @classmethod
    def movie_entities(
        cls,
        mid: str,
        *,
        relations: set[str] | None = None,
        actor_top_only: bool = False,
        with_relation_tokens: bool = False,
    ) -> dict[str, set[str]] | set[str]:
        cls.ensure_loaded()
        profile = cls._movie_profiles.get(mid)
        if not profile:
            return {} if with_relation_tokens else set()
        rels = relations or EXPANDED_RELATIONS
        if with_relation_tokens:
            data = {}
            for relation in rels:
                ids = profile.relation_entities(relation, actor_top_only=actor_top_only)
                data[relation] = {relation_token(relation, entity_id) for entity_id in ids}
            return data
        entities = set()
        for relation in rels:
            entities |= profile.relation_entities(relation, actor_top_only=actor_top_only)
        return entities

    @classmethod
    def build_triples(
        cls,
        *,
        use_expanded_relations: bool = True,
        include_inverse: bool = True,
    ) -> tuple[list[tuple[str, str, str]], set[str], dict[str, str], dict[str, tuple[str, str]]]:
        cls.ensure_loaded()
        cache_key = (use_expanded_relations, include_inverse)
        if cache_key in cls._triples_cache:
            return cls._triples_cache[cache_key]

        triples: list[tuple[str, str, str]] = []
        movie_mids = set(cls._movie_mids)
        entity_types: dict[str, str] = {}
        relation_types: dict[str, tuple[str, str]] = {}
        allowed_relations = EXPANDED_RELATIONS if use_expanded_relations else CORE_RELATIONS

        for mid, profile in cls._movie_profiles.items():
            movie_key = embed_entity_key("movie", mid)
            entity_types[movie_key] = "movie"
            for relation in allowed_relations:
                prefix = RELATION_TO_NODE_PREFIX[relation]
                rel_name = RELATION_TO_EMBED_EDGE[relation]
                head_type, tail_type = EMBED_EDGE_DIRECTIONS[relation]
                relation_types[rel_name] = (head_type, tail_type)
                if include_inverse:
                    relation_types[inverse_relation_name(rel_name)] = (tail_type, head_type)

                for entity_id in profile.relation_entities(relation, actor_top_only=False):
                    entity_key = embed_entity_key(prefix, entity_id)
                    entity_types[entity_key] = prefix
                    if head_type == "movie":
                        triples.append((movie_key, rel_name, entity_key))
                        if include_inverse:
                            triples.append((entity_key, inverse_relation_name(rel_name), movie_key))
                    else:
                        triples.append((entity_key, rel_name, movie_key))
                        if include_inverse:
                            triples.append((movie_key, inverse_relation_name(rel_name), entity_key))

        payload = (triples, movie_mids, entity_types, relation_types)
        cls._triples_cache[cache_key] = payload
        return payload

    @classmethod
    def _load(cls):
        cls._load_movies_from_mysql()
        cls._load_people_and_genres_from_neo4j()
        cls._build_relation_indexes()

    @classmethod
    def _load_movies_from_mysql(cls):
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT douban_id, name, genres, regions, languages, year, type "
                    "FROM movies WHERE douban_id IS NOT NULL"
                )
                rows = cursor.fetchall()
        finally:
            conn.close()

        movie_profiles: dict[str, MovieGraphProfile] = {}
        for row in rows:
            mid = str(row["douban_id"])
            profile = MovieGraphProfile(
                mid=mid,
                name=row.get("name") or mid,
                year=row.get("year"),
                content_type=(row.get("type") or "movie"),
                genres=parse_slash_tokens(row.get("genres")),
                regions=parse_slash_tokens(row.get("regions")),
                languages=parse_slash_tokens(row.get("languages")),
                year_bucket=build_year_bucket(row.get("year")),
            )
            movie_profiles[mid] = profile

        cls._movie_profiles = movie_profiles
        cls._movie_mids = sorted(movie_profiles)
        cls._movie_name_map = {mid: profile.name for mid, profile in movie_profiles.items()}

    @classmethod
    def _load_people_and_genres_from_neo4j(cls):
        driver = Neo4jConnection.get_driver()
        person_names: dict[str, str] = {}
        with driver.session() as session:
            directed_rows = session.run(
                "MATCH (p:Person)-[:DIRECTED]->(m:Movie) "
                "RETURN m.mid AS mid, collect(DISTINCT {pid: p.pid, name: p.name}) AS directors"
            )
            for row in directed_rows:
                profile = cls._movie_profiles.get(str(row["mid"]))
                if profile:
                    director_ids = set()
                    for director in row["directors"]:
                        pid = str(director.get("pid"))
                        if not pid:
                            continue
                        director_ids.add(pid)
                        if director.get("name"):
                            person_names[pid] = str(director["name"])
                    profile.directors = director_ids

            acted_rows = session.run(
                "MATCH (p:Person)-[rel:ACTED_IN]->(m:Movie) "
                "RETURN m.mid AS mid, p.pid AS pid, p.name AS name, coalesce(rel.order, 9999) AS ord "
                "ORDER BY mid, ord ASC"
            )
            for row in acted_rows:
                profile = cls._movie_profiles.get(str(row["mid"]))
                if not profile:
                    continue
                pid = str(row["pid"])
                profile.actors.add(pid)
                profile.actor_orders[pid] = min(
                    int(row["ord"]),
                    profile.actor_orders.get(pid, 9999),
                )
                if row.get("name"):
                    person_names[pid] = str(row["name"])
                if int(row["ord"]) <= 5:
                    profile.top_actors.add(pid)

            genre_rows = session.run(
                "MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre) "
                "RETURN m.mid AS mid, collect(DISTINCT g.name) AS genres"
            )
            for row in genre_rows:
                profile = cls._movie_profiles.get(str(row["mid"]))
                if profile:
                    profile.genres = {str(name) for name in row["genres"] if name}

        cls._person_name_map = person_names

    @classmethod
    def _build_relation_indexes(cls):
        inverted_index: dict[str, dict[str, set[str]]] = {
            relation: defaultdict(set) for relation in EXPANDED_RELATIONS
        }
        relation_degrees: dict[str, dict[str, int]] = {
            relation: {} for relation in EXPANDED_RELATIONS
        }

        for mid, profile in cls._movie_profiles.items():
            for relation in EXPANDED_RELATIONS:
                ids = profile.relation_entities(relation, actor_top_only=(relation == REL_ACTOR))
                for entity_id in ids:
                    inverted_index[relation][entity_id].add(mid)

        for relation, entity_movies in inverted_index.items():
            relation_degrees[relation] = {
                entity_id: len(mids) for entity_id, mids in entity_movies.items()
            }

        cls._relation_inverted_index = inverted_index
        cls._relation_degrees = relation_degrees
