import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "discover_public_douban_candidates.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("discover_public_douban_candidates", SCRIPT_PATH)
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
  <a href="/people/deleted/"><img alt="[已注销]"></a>
</body></html>
"""


def test_extract_contacts_skips_owner_deleted_and_duplicates():
    module = _load_script_module()

    rows = module._extract_contacts_from_html(CONTACTS_HTML, "owner")

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
