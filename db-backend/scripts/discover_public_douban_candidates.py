"""
Discover new public Douban profile candidates from seed users' contacts pages.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urljoin

from lxml import html

from app.services.douban_public_import import (
    build_http_client,
    extract_slug,
    fetch_text,
    load_user_specs,
    normalize_profile_url,
)


def _load_cookie_map(path: str | None) -> dict[str, str] | None:
    if not path:
        return None
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, list):
        cookie_map: dict[str, str] = {}
        for item in raw:
            if isinstance(item, dict) and item.get("name") and item.get("value"):
                cookie_map[str(item["name"])] = str(item["value"])
        return cookie_map or None
    raise ValueError("cookies 文件必须是 JSON 对象或 cookie 数组")


def _extract_contacts_from_html(html_text: str, owner_slug: str) -> list[dict]:
    doc = html.fromstring(html_text)
    seen: set[str] = set()
    candidates: list[dict] = []

    for anchor in doc.xpath("//a[contains(@href, '/people/')]"):
        href = anchor.get("href")
        if not href:
            continue
        full_url = urljoin("https://www.douban.com", href)
        try:
            slug = extract_slug(full_url)
        except ValueError:
            continue
        if slug == owner_slug or slug in seen:
            continue
        text_bits = [text.strip() for text in anchor.xpath(".//text()") if text.strip()]
        alt_bits = [text.strip() for text in anchor.xpath(".//img/@alt") if text.strip()]
        name = " ".join(text_bits or alt_bits) or None
        if name and "[已注销]" in name:
            continue
        seen.add(slug)
        candidates.append(
            {
                "slug": slug,
                "profile_url": normalize_profile_url(slug),
                "display_name": name,
                "discovered_from": owner_slug,
            }
        )

    return candidates


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover public Douban candidates from contacts pages.")
    parser.add_argument(
        "users",
        nargs="*",
        help="Seed Douban profile URLs or slugs.",
    )
    parser.add_argument(
        "--config",
        default="app/seed/public_douban_users.json",
        help="JSON config file containing seed profile_url entries.",
    )
    parser.add_argument(
        "--cookies-file",
        default=None,
        help="JSON file containing Douban cookies exported from a logged-in browser session.",
    )
    parser.add_argument(
        "--contacts-page-limit",
        type=int,
        default=1,
        help="How many contacts pages to fetch per seed user.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.5,
        help="Delay between contacts page requests.",
    )
    parser.add_argument(
        "--output",
        default="reports/public_douban_candidates.json",
        help="Where to write discovered candidate JSON.",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    specs = load_user_specs(args.config, args.users)
    if not specs:
        raise SystemExit("没有可用于发现候选的种子用户。")

    cookie_map = _load_cookie_map(args.cookies_file)
    discovered_by_slug: dict[str, dict] = {}
    seeds = {extract_slug(spec.profile_url) for spec in specs}

    with build_http_client(cookies=cookie_map) as client:
        for spec_index, spec in enumerate(specs):
            owner_slug = extract_slug(spec.profile_url)
            for page_index in range(args.contacts_page_limit):
                start = page_index * 45
                url = f"https://www.douban.com/people/{owner_slug}/contacts"
                if start:
                    url += f"?start={start}"
                html_text = fetch_text(client, url)
                page_candidates = _extract_contacts_from_html(html_text, owner_slug)
                new_count = 0
                for row in page_candidates:
                    if row["slug"] in seeds or row["slug"] in discovered_by_slug:
                        continue
                    discovered_by_slug[row["slug"]] = row
                    new_count += 1
                print(
                    f"{owner_slug} contacts page {page_index + 1}: "
                    f"{new_count} new / {len(page_candidates)} extracted"
                )
                if args.delay_seconds > 0 and (
                    page_index < args.contacts_page_limit - 1 or spec_index < len(specs) - 1
                ):
                    time.sleep(args.delay_seconds)

    payload = {
        "discovered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "contacts_page_limit": args.contacts_page_limit,
        "candidates": sorted(discovered_by_slug.values(), key=lambda row: row["slug"]),
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Discovered {len(payload['candidates'])} candidates.")
    print(f"JSON written to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
