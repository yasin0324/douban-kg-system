"""
CLI to harvest public Douban movie data and optionally sync it into MySQL.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from app.db.mysql import close_pool, get_connection, init_pool
from app.services.douban_public_import import (
    build_http_client,
    extract_slug,
    get_known_movie_mids,
    harvest_public_user,
    load_user_specs,
    upsert_bundle_to_db,
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


def _load_existing_output(path: Path) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    if not path.exists():
        return {}, {}, {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    users = {
        bundle["profile"]["slug"]: bundle
        for bundle in raw.get("users", [])
        if isinstance(bundle, dict) and bundle.get("profile", {}).get("slug")
    }
    db_results = {
        row["username"]: row
        for row in raw.get("db_results", [])
        if isinstance(row, dict) and row.get("username")
    }
    errors = {
        row["slug"]: row
        for row in raw.get("errors", [])
        if isinstance(row, dict) and row.get("slug")
    }
    return users, db_results, errors


def _bundle_is_complete(bundle: dict) -> bool:
    summary = bundle.get("summary", {})
    if summary.get("collect_capped") or summary.get("wish_capped"):
        return True
    collect_fetched_pages = summary.get("collect_fetched_pages")
    wish_fetched_pages = summary.get("wish_fetched_pages")
    collect_total_pages = summary.get("collect_total_pages")
    wish_total_pages = summary.get("wish_total_pages")
    collect_total = summary.get("collect_total_items")
    wish_total = summary.get("wish_total_items")
    collect_count = summary.get("collect_count", 0)
    wish_count = summary.get("wish_count", 0)

    if collect_fetched_pages is not None and collect_total_pages is not None:
        collect_done = collect_fetched_pages >= collect_total_pages
    else:
        collect_done = collect_total is None or collect_count >= collect_total * 0.95

    if wish_fetched_pages is not None and wish_total_pages is not None:
        wish_done = wish_fetched_pages >= wish_total_pages
    else:
        wish_done = wish_total is None or wish_count >= wish_total * 0.95
    return collect_done and wish_done


def _write_output(path: Path, harvested: list[dict], db_results: list[dict], errors: list[dict]) -> None:
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "users": harvested,
        "db_results": db_results,
        "errors": errors,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _maybe_sleep_between_users(delay_seconds: float, current_slug: str, has_more: bool) -> None:
    if delay_seconds <= 0 or not has_more:
        return
    print(f"Cooling down after {current_slug}: sleep {delay_seconds:.1f}s before next user...")
    time.sleep(delay_seconds)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import public Douban users into local JSON / MySQL.")
    parser.add_argument(
        "users",
        nargs="*",
        help="Douban profile URLs or slugs. Example: https://www.douban.com/people/guanyinan/",
    )
    parser.add_argument(
        "--config",
        default="app/seed/public_douban_users.json",
        help="JSON config file containing profile_url entries.",
    )
    parser.add_argument(
        "--output",
        default="reports/public_douban_users.json",
        help="Where to write harvested JSON.",
    )
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Upsert filtered results into local MySQL users / ratings / prefs tables.",
    )
    parser.add_argument(
        "--page-limit",
        type=int,
        default=None,
        help="Limit pages fetched per collect / wish list. Default fetches all pages.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.0,
        help="Delay between paginated list requests.",
    )
    parser.add_argument(
        "--between-users-seconds",
        type=float,
        default=0.0,
        help="Cooldown between users. Recommended when running multi-user batches against Douban.",
    )
    parser.add_argument(
        "--max-collect-items",
        type=int,
        default=None,
        help="Stop after collecting this many collect items for each user.",
    )
    parser.add_argument(
        "--max-wish-items",
        type=int,
        default=None,
        help="Stop after collecting this many wish items for each user.",
    )
    parser.add_argument(
        "--like-threshold",
        type=float,
        default=4.5,
        help="Collect ratings greater than or equal to this value will also be derived as like prefs.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Re-fetch users even if a complete bundle already exists in output JSON.",
    )
    parser.add_argument(
        "--cookies-file",
        default=None,
        help="JSON file containing Douban cookies exported from a logged-in browser session.",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    specs = load_user_specs(args.config, args.users)
    if not specs:
        raise SystemExit("没有可导入的豆瓣用户，请传入 URL/slug 或准备配置文件。")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing_users_by_slug, existing_db_results_by_username, existing_errors_by_slug = _load_existing_output(output_path)
    cookie_map = _load_cookie_map(args.cookies_file)

    harvested_by_slug: dict[str, dict] = dict(existing_users_by_slug)
    db_results_by_username: dict[str, dict] = dict(existing_db_results_by_username)
    errors_by_slug: dict[str, dict] = dict(existing_errors_by_slug)
    conn = None
    known_mids = None
    if args.write_db:
        init_pool()
        conn = get_connection()
        known_mids = get_known_movie_mids(conn)

    try:
        with build_http_client(cookies=cookie_map) as client:
            for index, spec in enumerate(specs):
                slug = extract_slug(spec.profile_url)
                existing_bundle = harvested_by_slug.get(slug)
                if existing_bundle and _bundle_is_complete(existing_bundle) and not args.force_refresh:
                    print(f"Skip complete bundle: {slug}")
                    if args.write_db:
                        db_result = upsert_bundle_to_db(conn, existing_bundle, known_mids=known_mids)
                        db_results_by_username[db_result["username"]] = db_result
                        _write_output(
                            output_path,
                            [harvested_by_slug[key] for key in sorted(harvested_by_slug)],
                            [db_results_by_username[key] for key in sorted(db_results_by_username)],
                            [errors_by_slug[key] for key in sorted(errors_by_slug)],
                        )
                    continue

                print(f"Harvesting: {slug}")
                has_more = index < len(specs) - 1
                try:
                    bundle = harvest_public_user(
                        client=client,
                        spec=spec,
                        delay_seconds=args.delay_seconds,
                        page_limit=args.page_limit,
                        max_collect_items=args.max_collect_items,
                        max_wish_items=args.max_wish_items,
                        derive_like_threshold=args.like_threshold,
                    )
                except Exception as exc:
                    print(f"Failed: {slug} -> {exc}")
                    errors_by_slug[slug] = {
                        "slug": slug,
                        "error": str(exc),
                        "failed_at": datetime.now().isoformat(timespec="seconds"),
                    }
                    _write_output(
                        output_path,
                        [harvested_by_slug[key] for key in sorted(harvested_by_slug)],
                        [db_results_by_username[key] for key in sorted(db_results_by_username)],
                        [errors_by_slug[key] for key in sorted(errors_by_slug)],
                    )
                    _maybe_sleep_between_users(args.between_users_seconds, slug, has_more)
                    continue

                harvested_by_slug[bundle["profile"]["slug"]] = bundle
                errors_by_slug.pop(bundle["profile"]["slug"], None)

                if args.write_db:
                    db_result = upsert_bundle_to_db(conn, bundle, known_mids=known_mids)
                    db_results_by_username[db_result["username"]] = db_result

                _write_output(
                    output_path,
                    [harvested_by_slug[key] for key in sorted(harvested_by_slug)],
                    [db_results_by_username[key] for key in sorted(db_results_by_username)],
                    [errors_by_slug[key] for key in sorted(errors_by_slug)],
                )
                _maybe_sleep_between_users(args.between_users_seconds, slug, has_more)
    finally:
        if conn is not None:
            conn.close()
            close_pool()

    harvested = [harvested_by_slug[key] for key in sorted(harvested_by_slug)]
    db_results = [db_results_by_username[key] for key in sorted(db_results_by_username)]
    errors = [errors_by_slug[key] for key in sorted(errors_by_slug)]

    print(f"Harvested {len(harvested)} public Douban users.")
    print(f"JSON written to: {output_path}")
    for row in db_results:
        print(
            f"- {row['username']}: user_id={row['user_id']} "
            f"ratings={row['ratings_written']} prefs={row['prefs_written']}"
        )
    if errors:
        print(f"Failed users: {len(errors)}")
        for row in errors:
            print(f"- {row['slug']}: {row['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
