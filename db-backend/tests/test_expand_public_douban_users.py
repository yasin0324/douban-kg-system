import importlib.util
import json
import sys
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Optional
from urllib.parse import urlparse


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "expand_public_douban_users.py"
)


def _install_dependency_stubs():
    app_module = ModuleType("app")
    db_module = ModuleType("app.db")
    mysql_module = ModuleType("app.db.mysql")
    services_module = ModuleType("app.services")
    import_module = ModuleType("app.services.douban_public_import")

    def _extract_slug(profile_or_slug: str) -> str:
        if "://" not in profile_or_slug:
            return profile_or_slug.strip("/ ")
        parsed = urlparse(profile_or_slug)
        parts = [part for part in parsed.path.split("/") if part]
        people_index = parts.index("people")
        return parts[people_index + 1]

    def _normalize_profile_url(profile_or_slug: str) -> str:
        slug = _extract_slug(profile_or_slug)
        return f"https://www.douban.com/people/{slug}/"

    @dataclass
    class _DoubanUserSpec:
        profile_url: str
        import_username: Optional[str] = None

    mysql_module.init_pool = lambda: None
    mysql_module.close_pool = lambda: None
    mysql_module.get_connection = lambda: None

    import_module.DoubanUserSpec = _DoubanUserSpec
    import_module.build_http_client = lambda cookies=None: None
    import_module.extract_slug = _extract_slug
    import_module.fetch_text = lambda client, url: ""
    import_module.get_known_movie_mids = lambda conn: set()
    import_module.harvest_public_user = lambda **kwargs: {}
    import_module.load_user_specs = lambda config_path, cli_values: []
    import_module.normalize_profile_url = _normalize_profile_url
    import_module.parse_profile_page = lambda html_text, slug: {"slug": slug, "movie_counts": {}}
    import_module.upsert_bundle_to_db = lambda conn, bundle, known_mids=None: {}

    app_module.db = db_module
    app_module.services = services_module
    db_module.mysql = mysql_module
    services_module.douban_public_import = import_module

    sys.modules["app"] = app_module
    sys.modules["app.db"] = db_module
    sys.modules["app.db.mysql"] = mysql_module
    sys.modules["app.services"] = services_module
    sys.modules["app.services.douban_public_import"] = import_module


def _load_script_module():
    _install_dependency_stubs()
    spec = importlib.util.spec_from_file_location("expand_public_douban_users", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CONTACTS_HTML = """
<html><body>
  <a href="https://www.douban.com/people/owner/">owner</a>
  <a href="https://www.douban.com/people/alice/"><img alt="alice">Alice</a>
  <a href="/people/bob/">Bob</a>
  <a href="/people/bob/">Bob Duplicate</a>
  <a href="/people/existing/">Existing</a>
</body></html>
"""


class _DummyClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_parse_args_defaults():
    module = _load_script_module()

    args = module.parse_args(["--cookies-file", "/tmp/douban_cookies.json"])

    assert args.target_eligible_users == 500
    assert args.candidate_categories == ["medium_native"]
    assert args.contacts_page_limit == 2
    assert args.import_delay_seconds == 6.0
    assert str(args.output_dir).startswith("reports/public_growth_runs/")


def test_load_seed_specs_merges_db_and_config(tmp_path, monkeypatch):
    module = _load_script_module()
    config_path = tmp_path / "seeds.json"
    config_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(
        module,
        "_load_existing_public_seed_specs",
        lambda: [
            {"profile_url": "https://www.douban.com/people/alice/"},
            {"profile_url": "https://www.douban.com/people/bob/"},
        ],
    )
    monkeypatch.setattr(
        module,
        "load_user_specs",
        lambda path, cli_values: [
            module.DoubanUserSpec(profile_url="https://www.douban.com/people/bob/"),
            module.DoubanUserSpec(profile_url="https://www.douban.com/people/carol/"),
        ],
    )

    seeds, existing_public_slugs = module._load_seed_specs(str(config_path))

    assert [module.extract_slug(row["profile_url"]) for row in seeds] == ["alice", "bob", "carol"]
    assert existing_public_slugs == {"alice", "bob"}


def test_count_eligible_public_users_uses_expected_rule(monkeypatch):
    module = _load_script_module()
    calls = []

    class FakeCursor:
        def execute(self, query, params):
            calls.append((query, params))

        def fetchone(self):
            return {"c": 123}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(module, "get_connection", lambda: FakeConn())

    assert module._count_eligible_public_users() == 123
    assert "COUNT(*) >= 3" in calls[0][0]
    assert "rating >= 3.5" in calls[0][0]
    assert calls[0][1] == (f"{module.PUBLIC_USER_PREFIX}_%",)


def test_discover_candidates_skips_existing_duplicates_and_owner(monkeypatch):
    module = _load_script_module()
    monkeypatch.setattr(module, "fetch_text", lambda client, url: CONTACTS_HTML)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    rows, errors = module._discover_candidates(
        client=_DummyClient(),
        seed_specs=[{"profile_url": "https://www.douban.com/people/owner/"}],
        existing_public_slugs={"existing"},
        contacts_page_limit=1,
        delay_seconds=0.0,
    )

    assert errors == []
    assert rows == [
        {
            "slug": "alice",
            "profile_url": "https://www.douban.com/people/alice/",
            "display_name": "Alice",
            "discovered_from": "owner",
        },
        {
            "slug": "bob",
            "profile_url": "https://www.douban.com/people/bob/",
            "display_name": "Bob",
            "discovered_from": "owner",
        },
    ]


def test_select_candidates_keeps_medium_native_only_and_sorts():
    module = _load_script_module()
    screened = [
        {
            "slug": "z",
            "category": "medium_native",
            "collect_total": 300,
            "wish_total": 50,
            "recommended_max_collect_items": 300,
            "recommended_max_wish_items": 50,
        },
        {
            "slug": "a",
            "category": "light_native",
            "collect_total": 60,
            "wish_total": 10,
            "recommended_max_collect_items": 60,
            "recommended_max_wish_items": 10,
        },
        {
            "slug": "b",
            "category": "medium_native",
            "collect_total": 300,
            "wish_total": 120,
            "recommended_max_collect_items": 300,
            "recommended_max_wish_items": 120,
        },
    ]

    selected = module._select_candidates(
        screened,
        candidate_categories=["medium_native"],
        max_collect_items=300,
        max_wish_items=120,
    )

    assert [row["slug"] for row in selected] == ["b", "z"]


def test_apply_import_caps_clamps_collect_and_wish():
    module = _load_script_module()

    payload = module._apply_import_caps(
        {
            "slug": "sample",
            "recommended_max_collect_items": 300,
            "recommended_max_wish_items": 160,
        },
        max_collect_items=300,
        max_wish_items=120,
    )

    assert payload["selected_max_collect_items"] == 300
    assert payload["selected_max_wish_items"] == 120


def test_main_exits_early_when_target_already_met(tmp_path, monkeypatch):
    module = _load_script_module()
    output_dir = tmp_path / "run"

    monkeypatch.setattr(
        module,
        "parse_args",
        lambda argv=None: Namespace(
            target_eligible_users=500,
            cookies_file="/tmp/douban_cookies.json",
            seed_config=None,
            contacts_page_limit=2,
            discover_delay_seconds=1.5,
            screen_delay_seconds=1.0,
            import_delay_seconds=6.0,
            between_users_seconds=90.0,
            max_collect_items=300,
            max_wish_items=120,
            candidate_categories=["medium_native"],
            output_dir=str(output_dir),
        ),
    )
    monkeypatch.setattr(module, "init_pool", lambda: None)
    monkeypatch.setattr(module, "close_pool", lambda: None)
    monkeypatch.setattr(
        module,
        "_load_seed_specs",
        lambda seed_config: (
            [{"profile_url": "https://www.douban.com/people/alice/"}],
            {"alice"},
        ),
    )
    monkeypatch.setattr(module, "_count_eligible_public_users", lambda: 500)

    assert module.main() == 0

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["stop_reason"] == "target_reached"
    assert summary["eligible_users_before"] == 500
    assert summary["selected_count"] == 0


def test_main_stops_after_target_reached_mid_import(tmp_path, monkeypatch):
    module = _load_script_module()
    output_dir = tmp_path / "run"
    eligible_counts = iter([210, 500])
    screen_calls = []

    monkeypatch.setattr(
        module,
        "parse_args",
        lambda argv=None: Namespace(
            target_eligible_users=500,
            cookies_file="/tmp/douban_cookies.json",
            seed_config=None,
            contacts_page_limit=2,
            discover_delay_seconds=1.5,
            screen_delay_seconds=1.0,
            import_delay_seconds=6.0,
            between_users_seconds=0.0,
            max_collect_items=300,
            max_wish_items=120,
            candidate_categories=["medium_native"],
            output_dir=str(output_dir),
        ),
    )
    monkeypatch.setattr(module, "SCREEN_IMPORT_BATCH_SIZE", 1)
    monkeypatch.setattr(module, "init_pool", lambda: None)
    monkeypatch.setattr(module, "close_pool", lambda: None)
    monkeypatch.setattr(
        module,
        "_load_seed_specs",
        lambda seed_config: (
            [{"profile_url": "https://www.douban.com/people/alice/"}],
            {"alice"},
        ),
    )
    monkeypatch.setattr(module, "_count_eligible_public_users", lambda: next(eligible_counts))
    monkeypatch.setattr(module, "_load_known_movie_mids", lambda: {"m1"})
    monkeypatch.setattr(module, "_load_cookie_map", lambda path: {"dbcl2": "cookie"})
    monkeypatch.setattr(module, "build_http_client", lambda cookies=None: _DummyClient())
    monkeypatch.setattr(
        module,
        "_discover_candidates",
        lambda **kwargs: (
            [
                {"slug": "c1", "profile_url": "https://www.douban.com/people/c1/"},
                {"slug": "c2", "profile_url": "https://www.douban.com/people/c2/"},
            ],
            [],
        ),
    )

    def fake_screen_candidates(*, candidates, **kwargs):
        screen_calls.append([row["slug"] for row in candidates])
        screened = []
        for row in candidates:
            screened.append(
                {
                    "slug": row["slug"],
                    "profile_url": row["profile_url"],
                    "category": "medium_native",
                    "collect_total": 200 if row["slug"] == "c1" else 180,
                    "wish_total": 80 if row["slug"] == "c1" else 70,
                    "recommended_max_collect_items": 200 if row["slug"] == "c1" else 180,
                    "recommended_max_wish_items": 80 if row["slug"] == "c1" else 70,
                }
            )
        return screened, []

    monkeypatch.setattr(module, "_screen_candidates", fake_screen_candidates)
    monkeypatch.setattr(
        module,
        "harvest_public_user",
        lambda **kwargs: {"profile": {"slug": module.extract_slug(kwargs["spec"].profile_url)}},
    )

    class FakeConn:
        def close(self):
            return None

    monkeypatch.setattr(module, "get_connection", lambda: FakeConn())
    monkeypatch.setattr(
        module,
        "upsert_bundle_to_db",
        lambda conn, bundle, known_mids=None: {
            "user_id": 1,
            "username": f"douban_public_{bundle['profile']['slug']}",
            "ratings_written": 10,
            "prefs_written": 3,
        },
    )

    assert module.main() == 0

    results = json.loads((output_dir / "import_results.json").read_text(encoding="utf-8"))
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))

    assert len(results["results"]) == 1
    assert summary["imported_count"] == 1
    assert summary["stop_reason"] == "target_reached"
    assert summary["screened_count"] == 1
    assert screen_calls == [["c1"]]


def test_main_continues_after_import_failure(tmp_path, monkeypatch):
    module = _load_script_module()
    output_dir = tmp_path / "run"
    eligible_counts = iter([210, 211])

    monkeypatch.setattr(
        module,
        "parse_args",
        lambda argv=None: Namespace(
            target_eligible_users=500,
            cookies_file="/tmp/douban_cookies.json",
            seed_config=None,
            contacts_page_limit=2,
            discover_delay_seconds=1.5,
            screen_delay_seconds=1.0,
            import_delay_seconds=6.0,
            between_users_seconds=0.0,
            max_collect_items=300,
            max_wish_items=120,
            candidate_categories=["medium_native"],
            output_dir=str(output_dir),
        ),
    )
    monkeypatch.setattr(module, "SCREEN_IMPORT_BATCH_SIZE", 1)
    monkeypatch.setattr(module, "init_pool", lambda: None)
    monkeypatch.setattr(module, "close_pool", lambda: None)
    monkeypatch.setattr(
        module,
        "_load_seed_specs",
        lambda seed_config: (
            [{"profile_url": "https://www.douban.com/people/alice/"}],
            {"alice"},
        ),
    )
    monkeypatch.setattr(module, "_count_eligible_public_users", lambda: next(eligible_counts))
    monkeypatch.setattr(module, "_load_known_movie_mids", lambda: {"m1"})
    monkeypatch.setattr(module, "_load_cookie_map", lambda path: {"dbcl2": "cookie"})
    monkeypatch.setattr(module, "build_http_client", lambda cookies=None: _DummyClient())
    monkeypatch.setattr(
        module,
        "_discover_candidates",
        lambda **kwargs: (
            [
                {
                    "slug": "c1",
                    "profile_url": "https://www.douban.com/people/c1/",
                },
                {
                    "slug": "c2",
                    "profile_url": "https://www.douban.com/people/c2/",
                },
            ],
            [],
        ),
    )

    def fake_screen_candidates(*, candidates, **kwargs):
        screened = []
        for row in candidates:
            screened.append(
                {
                    "slug": row["slug"],
                    "profile_url": row["profile_url"],
                    "category": "medium_native",
                    "collect_total": 200 if row["slug"] == "c1" else 180,
                    "wish_total": 80 if row["slug"] == "c1" else 70,
                    "recommended_max_collect_items": 200 if row["slug"] == "c1" else 180,
                    "recommended_max_wish_items": 80 if row["slug"] == "c1" else 70,
                }
            )
        return screened, []

    monkeypatch.setattr(module, "_screen_candidates", fake_screen_candidates)

    calls = {"count": 0}

    def fake_harvest_public_user(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("403")
        return {"profile": {"slug": module.extract_slug(kwargs["spec"].profile_url)}}

    monkeypatch.setattr(module, "harvest_public_user", fake_harvest_public_user)

    class FakeConn:
        def close(self):
            return None

    monkeypatch.setattr(module, "get_connection", lambda: FakeConn())
    monkeypatch.setattr(
        module,
        "upsert_bundle_to_db",
        lambda conn, bundle, known_mids=None: {
            "user_id": 2,
            "username": "douban_public_c2",
            "ratings_written": 8,
            "prefs_written": 2,
        },
    )

    assert module.main() == 0

    results = json.loads((output_dir / "import_results.json").read_text(encoding="utf-8"))
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))

    assert len(results["results"]) == 2
    assert results["results"][0]["status"] == "failed"
    assert results["results"][1]["status"] == "imported"
    assert summary["failed_count"] == 1
    assert summary["imported_count"] == 1
    assert summary["stop_reason"] == "candidate_exhausted"
