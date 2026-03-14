"""
Screen public Douban profile pages and classify candidates for medium-sized imports.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.services.douban_public_import import (
    build_http_client,
    extract_slug,
    fetch_text,
    load_user_specs,
    normalize_profile_url,
    parse_profile_page,
)


LIGHT_NATIVE_COLLECT_MIN = 20
LIGHT_NATIVE_COLLECT_MAX = 80
LIGHT_NATIVE_WISH_MIN = 5
LIGHT_NATIVE_WISH_MAX = 50
MEDIUM_NATIVE_COLLECT_MAX = 800
MEDIUM_NATIVE_WISH_MAX = 400
MIN_USABLE_COLLECT = 20
MIN_USABLE_TOTAL = 30
DEFAULT_CAPPED_COLLECT = 300
DEFAULT_CAPPED_WISH = 200


@dataclass
class ScreenedCandidate:
    slug: str
    profile_url: str
    display_name: str | None
    collect_total: int
    wish_total: int
    total_interactions: int
    category: str
    recommended_max_collect_items: int | None
    recommended_max_wish_items: int | None


def classify_candidate(profile: dict) -> ScreenedCandidate:
    counts = profile.get("movie_counts") or {}
    collect_total = int(counts.get("collect") or 0)
    wish_total = int(counts.get("wish") or 0)
    total_interactions = collect_total + wish_total

    if collect_total < MIN_USABLE_COLLECT and total_interactions < MIN_USABLE_TOTAL:
        category = "too_light"
        max_collect = None
        max_wish = None
    elif (
        LIGHT_NATIVE_COLLECT_MIN <= collect_total <= LIGHT_NATIVE_COLLECT_MAX
        and wish_total <= LIGHT_NATIVE_WISH_MAX
    ) or (
        collect_total < LIGHT_NATIVE_COLLECT_MIN
        and LIGHT_NATIVE_WISH_MIN <= wish_total <= LIGHT_NATIVE_WISH_MAX
    ):
        category = "light_native"
        max_collect = min(collect_total, LIGHT_NATIVE_COLLECT_MAX) or None
        max_wish = min(wish_total, LIGHT_NATIVE_WISH_MAX) or None
    elif collect_total <= MEDIUM_NATIVE_COLLECT_MAX and wish_total <= MEDIUM_NATIVE_WISH_MAX:
        category = "medium_native"
        max_collect = min(collect_total, DEFAULT_CAPPED_COLLECT) or None
        max_wish = min(wish_total, DEFAULT_CAPPED_WISH) or None
    else:
        category = "heavy_capped"
        max_collect = DEFAULT_CAPPED_COLLECT if collect_total else None
        max_wish = DEFAULT_CAPPED_WISH if wish_total else None

    return ScreenedCandidate(
        slug=profile["slug"],
        profile_url=normalize_profile_url(profile["slug"]),
        display_name=profile.get("display_name"),
        collect_total=collect_total,
        wish_total=wish_total,
        total_interactions=total_interactions,
        category=category,
        recommended_max_collect_items=max_collect,
        recommended_max_wish_items=max_wish,
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen public Douban users for medium-sized imports.")
    parser.add_argument(
        "users",
        nargs="*",
        help="Douban profile URLs or slugs.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional JSON config file containing profile_url entries.",
    )
    parser.add_argument(
        "--cookies-file",
        default=None,
        help="JSON file containing Douban cookies exported from a logged-in browser session.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.0,
        help="Delay between profile requests.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional JSON file to write screening results.",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    config_path = args.config or "app/seed/public_douban_users.json"
    specs = load_user_specs(config_path if Path(config_path).exists() else None, args.users)
    if not specs:
        raise SystemExit("没有可筛选的豆瓣用户，请传入 URL/slug 或准备配置文件。")

    cookie_map = _load_cookie_map(args.cookies_file)
    screened: list[dict] = []
    errors: list[dict] = []

    with build_http_client(cookies=cookie_map) as client:
        for index, spec in enumerate(specs):
            slug = extract_slug(spec.profile_url)
            try:
                profile_html = fetch_text(client, normalize_profile_url(slug))
                candidate = classify_candidate(parse_profile_page(profile_html, slug))
            except Exception as exc:
                errors.append(
                    {
                        "slug": slug,
                        "profile_url": normalize_profile_url(slug),
                        "error": str(exc),
                    }
                )
                print(f"{slug}: error -> {exc}")
            else:
                screened.append(asdict(candidate))
                print(
                    f"{candidate.slug}: {candidate.category} "
                    f"collect={candidate.collect_total} wish={candidate.wish_total} "
                    f"cap=({candidate.recommended_max_collect_items},{candidate.recommended_max_wish_items})"
                )
            if args.delay_seconds > 0 and index < len(specs) - 1:
                time.sleep(args.delay_seconds)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "screened_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "candidates": screened,
            "errors": errors,
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON written to: {output_path}")

    if errors:
        print(f"Failed candidates: {len(errors)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
