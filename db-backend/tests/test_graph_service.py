from app.services import graph_service


class FakeNode(dict):
    def __init__(self, labels, **props):
        super().__init__(props)
        self.labels = {labels} if isinstance(labels, str) else set(labels)


class FakeRelationship:
    def __init__(self, rel_type, start_node=None, end_node=None):
        self.type = rel_type
        self.start_node = start_node
        self.end_node = end_node


class FakePath:
    def __init__(self, nodes, relationships):
        self.nodes = list(nodes)
        self.relationships = list(relationships)


class FakeListSession:
    def __init__(self, records):
        self._records = list(records)
        self.queries = []

    def begin_transaction(self, timeout=None):
        raise TypeError

    def run(self, query, **params):
        self.queries.append((query, params))
        return list(self._records)


class FakeSingleResult:
    def __init__(self, record):
        self._record = record

    def single(self):
        return self._record


class FakePathSession:
    def __init__(self, record):
        self._record = record
        self.queries = []

    def run(self, query, **params):
        self.queries.append((query, params))
        return FakeSingleResult(self._record)


def test_get_movie_graph_filters_out_recommendation_only_nodes():
    movie = FakeNode("Movie", mid="m1", title="Movie 1", rating=8.4, year=2024)
    genre = FakeNode("Genre", name="剧情")
    region = FakeNode("Region", name="中国")
    genre_rel = FakeRelationship("HAS_GENRE", start_node=movie, end_node=genre)
    region_rel = FakeRelationship("IN_REGION", start_node=movie, end_node=region)
    session = FakeListSession(
        [
            {
                "m": movie,
                "edges1": [
                    {"node": genre, "rel": genre_rel},
                    {"node": region, "rel": region_rel},
                ],
                "edges2": [],
            }
        ]
    )

    payload = graph_service.get_movie_graph(session, mid="m1")

    assert {node["type"] for node in payload["nodes"]} == {"Movie", "Genre"}
    assert all(edge["type"] in graph_service.PUBLIC_GRAPH_REL_TYPES for edge in payload["edges"])
    assert all(node["type"] != "Region" for node in payload["nodes"])


def test_get_person_graph_filters_out_recommendation_only_nodes():
    person = FakeNode("Person", pid="p1", name="Actor 1", profession="演员")
    movie = FakeNode("Movie", mid="m1", title="Movie 1", year=2024)
    language = FakeNode("Language", name="汉语")
    acted_in = FakeRelationship("ACTED_IN", start_node=person, end_node=movie)
    in_language = FakeRelationship("IN_LANGUAGE", start_node=movie, end_node=language)
    session = FakeListSession(
        [
            {
                "p": person,
                "edges1": [
                    {"node": movie, "rel": acted_in},
                    {"node": language, "rel": in_language},
                ],
                "edges2": [],
            }
        ]
    )

    payload = graph_service.get_person_graph(session, pid="p1")

    assert {node["type"] for node in payload["nodes"]} == {"Person", "Movie"}
    assert all(edge["type"] in graph_service.PUBLIC_GRAPH_REL_TYPES for edge in payload["edges"])
    assert all(node["type"] != "Language" for node in payload["nodes"])


def test_find_shortest_path_restricts_to_public_graph_relations():
    movie1 = FakeNode("Movie", mid="m1", title="Movie 1")
    genre = FakeNode("Genre", name="剧情")
    movie2 = FakeNode("Movie", mid="m2", title="Movie 2")
    path = FakePath(
        nodes=[movie1, genre, movie2],
        relationships=[
            FakeRelationship("HAS_GENRE", start_node=movie1, end_node=genre),
            FakeRelationship("HAS_GENRE", start_node=genre, end_node=movie2),
        ],
    )
    session = FakePathSession({"path": path})

    payload = graph_service.find_shortest_path(session, from_id="m1", to_id="m2")

    assert {node["type"] for node in payload["nodes"]} == {"Movie", "Genre"}
    query = session.queries[0][0]
    rel_pattern = "|".join(sorted(graph_service.PUBLIC_GRAPH_REL_TYPES))
    assert f"[:{rel_pattern}*..6]" in query
    assert "[*..6]" not in query
    assert "(start:Movie OR start:Person OR start:Genre)" in query


def test_find_shortest_path_returns_empty_for_recommendation_only_entities():
    movie1 = FakeNode("Movie", mid="m1", title="Movie 1")
    region = FakeNode("Region", name="中国")
    movie2 = FakeNode("Movie", mid="m2", title="Movie 2")
    path = FakePath(
        nodes=[movie1, region, movie2],
        relationships=[
            FakeRelationship("IN_REGION", start_node=movie1, end_node=region),
            FakeRelationship("IN_REGION", start_node=region, end_node=movie2),
        ],
    )
    session = FakePathSession({"path": path})

    payload = graph_service.find_shortest_path(session, from_id="m1", to_id="m2")

    assert payload["nodes"] == []
    assert payload["edges"] == []
    assert payload["meta"]["node_count"] == 0
    assert payload["meta"]["edge_count"] == 0


def test_find_shortest_path_exclude_genre_keeps_person_only_relations():
    person1 = FakeNode("Person", pid="p1", name="Actor 1")
    movie = FakeNode("Movie", mid="m1", title="Movie 1")
    person2 = FakeNode("Person", pid="p2", name="Actor 2")
    path = FakePath(
        nodes=[person1, movie, person2],
        relationships=[
            FakeRelationship("ACTED_IN", start_node=person1, end_node=movie),
            FakeRelationship("ACTED_IN", start_node=movie, end_node=person2),
        ],
    )
    session = FakePathSession({"path": path})

    payload = graph_service.find_shortest_path(
        session,
        from_id="p1",
        to_id="p2",
        exclude_genre=True,
    )

    assert {node["type"] for node in payload["nodes"]} == {"Movie", "Person"}
    query = session.queries[0][0]
    rel_pattern = "|".join(sorted(graph_service.PERSON_ONLY_GRAPH_REL_TYPES))
    assert f"[:{rel_pattern}*..6]" in query
    assert "HAS_GENRE" not in query
