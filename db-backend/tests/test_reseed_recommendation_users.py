from statistics import mean

from app.seed import recommendation_users as seed_users


def build_sample_movies():
    themes = [
        (("科幻", "悬疑"), ("美国",), 2016, 8.8, 600000),
        (("动作", "犯罪"), ("美国",), 2014, 8.3, 420000),
        (("动画", "奇幻"), ("日本",), 2018, 8.6, 380000),
        (("喜剧", "家庭"), ("中国大陆",), 2015, 7.9, 260000),
        (("纪录片", "历史"), ("英国",), 2012, 8.2, 120000),
        (("剧情", "爱情"), ("法国",), 2011, 8.4, 180000),
        (("家庭", "剧情"), ("中国大陆",), 2019, 8.1, 150000),
        (("恐怖", "惊悚"), ("美国",), 2013, 6.8, 90000),
    ]

    movies = []
    counter = 1000
    for theme_index, (genres, regions, year, score, votes) in enumerate(themes):
        for variant in range(8):
            counter += 1
            movies.append(
                seed_users.MovieCandidate(
                    mid=str(counter),
                    title=f"movie_{theme_index}_{variant}",
                    genres=genres,
                    regions=regions,
                    languages=("英语",) if "美国" in regions or "英国" in regions else ("中文",),
                    year=year + (variant % 3),
                    release_date=f"{year + (variant % 3)}-0{(variant % 8) + 1}-01",
                    douban_score=round(score - variant * 0.05, 2),
                    douban_votes=votes - variant * 3000,
                )
            )
    return movies


class FakeResult:
    def consume(self):
        return None


class FakeSession:
    def __init__(self, statements):
        self.statements = statements

    def run(self, query, **params):
        self.statements.append((" ".join(query.split()), params))
        return FakeResult()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeDriver:
    def __init__(self):
        self.statements = []

    def session(self):
        return FakeSession(self.statements)


class RecordingCursor:
    def __init__(self, conn):
        self.conn = conn
        self._fetchone = None
        self._fetchall = []
        self.lastrowid = None

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.conn.queries.append((normalized, params))
        if normalized.startswith("SELECT id FROM users ORDER BY id ASC"):
            self._fetchall = self.conn.fetchall_queue.pop(0) if self.conn.fetchall_queue else []
        elif normalized.startswith("SELECT id FROM users WHERE username = %s"):
            self._fetchone = self.conn.fetchone_queue.pop(0) if self.conn.fetchone_queue else None
        elif normalized.startswith("INSERT INTO users"):
            self.lastrowid = self.conn.next_lastrowid
            self.conn.next_lastrowid += 1

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return self._fetchall

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class RecordingConn:
    def __init__(self, *, fetchone_queue=None, fetchall_queue=None, start_lastrowid=100):
        self.fetchone_queue = list(fetchone_queue or [])
        self.fetchall_queue = list(fetchall_queue or [])
        self.next_lastrowid = start_lastrowid
        self.queries = []
        self.commit_count = 0

    def cursor(self):
        return RecordingCursor(self)

    def commit(self):
        self.commit_count += 1


def test_movie_from_row_rejects_unreleased_or_invalid_rows():
    unreleased = {
        "douban_id": "1",
        "name": "future_movie",
        "genres": "科幻/悬疑",
        "regions": "美国",
        "languages": "英语",
        "year": 2026,
        "release_date": "2026-09-01",
        "douban_score": 8.2,
        "douban_votes": 1000,
    }
    missing_genres = {
        "douban_id": "2",
        "name": "broken_movie",
        "genres": "",
        "regions": "美国",
        "languages": "英语",
        "year": 2024,
        "release_date": "2024-01-01",
        "douban_score": 7.5,
        "douban_votes": 1000,
    }
    valid = {
        "douban_id": "3",
        "name": "valid_movie",
        "genres": "剧情/爱情",
        "regions": "法国",
        "languages": "法语",
        "year": 2024,
        "release_date": "2024-02-01",
        "douban_score": 8.6,
        "douban_votes": 2000,
    }

    assert seed_users.movie_from_row(unreleased) is None
    assert seed_users.movie_from_row(missing_genres) is None
    movie = seed_users.movie_from_row(valid)
    assert movie is not None
    assert movie.mid == "3"
    assert movie.genres == ("剧情", "爱情")


def test_deterministic_user_respects_persona_signal():
    movies = build_sample_movies()
    persona = seed_users.resolve_personas("scifi_thriller")[0]
    persona_pool = seed_users.build_persona_movie_buckets(movies, persona)
    user = seed_users.build_deterministic_user(
        persona=persona,
        persona_pool=persona_pool,
        global_index=7,
        persona_index=0,
        username_prefix="seed_cfkg",
    )
    movie_lookup = {movie.mid: movie for movie in movies}
    failures = seed_users.validate_generated_user(user, persona, movie_lookup)

    preferred_scores = [
        item.rating
        for item in user.ratings
        if set(movie_lookup[item.mid].genres) & set(persona.strong_genres)
    ]
    avoided_scores = [
        item.rating
        for item in user.ratings
        if set(movie_lookup[item.mid].genres) & set(persona.avoid_genres)
    ]

    assert not (set(user.likes) & set(user.wants))
    assert not (set(user.wants) & {item.mid for item in user.ratings})
    assert mean(preferred_scores) > mean(avoided_scores)
    assert "persona_preference_not_clear" not in failures
    assert "likes_not_backed_by_positive_ratings" not in failures


def test_generate_seed_users_builds_quality_report_for_dry_run_shape():
    movies = build_sample_movies()
    users, movie_lookup, persona_lookup = seed_users.generate_recommendation_seed_users(
        movies=movies,
        user_count=10,
        persona_set="scifi_thriller,drama_romance",
        username_prefix="seed_cfkg",
        llm_provider="none",
        seed=11,
    )
    report = seed_users.build_quality_report(
        users=users,
        movie_lookup=movie_lookup,
        persona_lookup=persona_lookup,
        dry_run=True,
        clear_existing=True,
        is_mock=False,
    )

    assert len(users) == 10
    assert report["user_count"] == 10
    assert report["rating_count"] >= 150
    assert report["like_count"] >= 40
    assert report["want_count"] >= 30
    assert report["profile_usability"]["clear_positive_preference_ratio"] > 0
    assert report["profile_usability"]["time_split_ready_ratio"] > 0


def test_clear_ordinary_users_removes_admin_audit_rows_before_users():
    conn = RecordingConn(fetchall_queue=[[{"id": 1}, {"id": 2}]])
    driver = FakeDriver()

    summary = seed_users.clear_ordinary_users(conn, driver)

    assert summary["deleted_user_count"] == 2
    assert "DELETE FROM admin_user_actions WHERE target_user_id IN (%s, %s)" in conn.queries[1][0]
    assert "DELETE FROM users WHERE id IN (%s, %s)" in conn.queries[2][0]
    assert any("DETACH DELETE u" in query for query, _ in driver.statements)


def test_persist_generated_users_writes_mysql_and_neo4j():
    conn = RecordingConn(fetchone_queue=[None], start_lastrowid=321)
    driver = FakeDriver()
    user = seed_users.GeneratedUserData(
        username="seed_cfkg_scifi_thriller_001",
        nickname="科幻悬疑派1",
        persona="科幻悬疑派",
        persona_slug="scifi_thriller",
        ratings=[
            seed_users.GeneratedRating(mid="1001", rating=4.5, rationale_tag="strong_match", rated_at="2025-01-01 12:00:00"),
            seed_users.GeneratedRating(mid="1002", rating=2.0, rationale_tag="avoidance_signal", rated_at="2025-01-05 12:00:00"),
        ],
        likes=["1001"],
        wants=["1003"],
        generation_mode="deterministic",
    )

    summary = seed_users.persist_generated_users(conn, driver, [user], is_mock=False)

    assert summary == {
        "inserted_users": 1,
        "inserted_ratings": 2,
        "inserted_preferences": 2,
    }
    assert any("INSERT INTO users" in sql for sql, _ in conn.queries)
    assert any("INSERT INTO user_movie_ratings" in sql for sql, _ in conn.queries)
    assert any("INSERT INTO user_movie_prefs" in sql for sql, _ in conn.queries)
    assert any("MERGE (u:User {id: $uid})" in query for query, _ in driver.statements)
    assert any("MERGE (u)-[rel:RATED]->(m)" in query for query, _ in driver.statements)
