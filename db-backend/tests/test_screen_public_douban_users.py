import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "screen_public_douban_users.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("screen_public_douban_users", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_classify_candidate_prefers_medium_native():
    module = _load_script_module()

    candidate = module.classify_candidate(
        {
            "slug": "sample_user",
            "movie_counts": {
                "collect": 420,
                "wish": 160,
            },
        }
    )

    assert candidate.category == "medium_native"
    assert candidate.recommended_max_collect_items == 300
    assert candidate.recommended_max_wish_items == 160


def test_classify_candidate_keeps_light_native_users():
    module = _load_script_module()

    candidate = module.classify_candidate(
        {
            "slug": "light_user",
            "movie_counts": {
                "collect": 48,
                "wish": 18,
            },
        }
    )

    assert candidate.category == "light_native"
    assert candidate.recommended_max_collect_items == 48
    assert candidate.recommended_max_wish_items == 18


def test_classify_candidate_caps_heavy_users():
    module = _load_script_module()

    candidate = module.classify_candidate(
        {
            "slug": "heavy_user",
            "movie_counts": {
                "collect": 2400,
                "wish": 900,
            },
        }
    )

    assert candidate.category == "heavy_capped"
    assert candidate.recommended_max_collect_items == 300
    assert candidate.recommended_max_wish_items == 200


def test_classify_candidate_does_not_mark_large_collect_as_light():
    module = _load_script_module()

    candidate = module.classify_candidate(
        {
            "slug": "collect_heavy_user",
            "movie_counts": {
                "collect": 311,
                "wish": 11,
            },
        }
    )

    assert candidate.category == "medium_native"
    assert candidate.recommended_max_collect_items == 300
    assert candidate.recommended_max_wish_items == 11


def test_parse_args_for_screen_script():
    module = _load_script_module()

    args = module.parse_args(
        [
            "--config",
            "app/seed/public_douban_users.json",
            "--delay-seconds",
            "2",
            "--output",
            "reports/screen.json",
            "https://www.douban.com/people/guanyinan/",
        ]
    )

    assert args.config == "app/seed/public_douban_users.json"
    assert args.delay_seconds == 2.0
    assert args.output == "reports/screen.json"
    assert args.users == ["https://www.douban.com/people/guanyinan/"]


def test_screen_script_continues_on_profile_errors(tmp_path, monkeypatch):
    module = _load_script_module()
    config_path = tmp_path / "batch.json"
    output_path = tmp_path / "screened.json"
    config_path.write_text(
        json.dumps(
            [
                {"profile_url": "https://www.douban.com/people/good_user/"},
                {"profile_url": "https://www.douban.com/people/missing_user/"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class DummyClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_fetch_text(client, url):
        if "missing_user" in url:
            raise RuntimeError("404 Not Found")
        return "<html></html>"

    def fake_parse_profile_page(html_text, slug):
        return {
            "slug": slug,
            "display_name": slug,
            "movie_counts": {"collect": 120, "wish": 40},
        }

    monkeypatch.setattr(module, "build_http_client", lambda cookies=None: DummyClient())
    monkeypatch.setattr(module, "fetch_text", fake_fetch_text)
    monkeypatch.setattr(module, "parse_profile_page", fake_parse_profile_page)
    monkeypatch.setattr(
        module,
        "parse_args",
        lambda argv=None: module.argparse.Namespace(
            users=[],
            config=str(config_path),
            cookies_file=None,
            delay_seconds=0.0,
            output=str(output_path),
        ),
    )

    assert module.main() == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert [row["slug"] for row in payload["candidates"]] == ["good_user"]
    assert payload["errors"] == [
        {
            "slug": "missing_user",
            "profile_url": "https://www.douban.com/people/missing_user/",
            "error": "404 Not Found",
        }
    ]
