import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "import_public_douban_users.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("import_public_douban_users", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_args_accepts_between_users_seconds():
    module = _load_script_module()

    args = module.parse_args(
        [
            "--between-users-seconds",
            "120",
            "--delay-seconds",
            "6",
            "--max-collect-items",
            "300",
            "--max-wish-items",
            "120",
            "https://www.douban.com/people/guanyinan/",
        ]
    )

    assert args.between_users_seconds == 120.0
    assert args.delay_seconds == 6.0
    assert args.max_collect_items == 300
    assert args.max_wish_items == 120
    assert args.users == ["https://www.douban.com/people/guanyinan/"]


def test_maybe_sleep_between_users_only_when_needed(monkeypatch):
    module = _load_script_module()
    calls: list[float] = []

    monkeypatch.setattr(module.time, "sleep", lambda seconds: calls.append(seconds))

    module._maybe_sleep_between_users(90.0, "guanyinan", has_more=True)
    module._maybe_sleep_between_users(90.0, "guanyinan", has_more=False)
    module._maybe_sleep_between_users(0.0, "guanyinan", has_more=True)

    assert calls == [90.0]


def test_bundle_is_complete_accepts_capped_imports():
    module = _load_script_module()

    assert module._bundle_is_complete(
        {
            "summary": {
                "collect_capped": True,
                "wish_capped": False,
                "collect_fetched_pages": 3,
                "collect_total_pages": 99,
            }
        }
    )
