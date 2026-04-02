"""
Orchestrate public Douban user expansion until the offline-evaluable user target is reached.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from lxml import html

from app.db.mysql import close_pool, get_connection, init_pool
from app.services.douban_public_import import (
    DoubanUserSpec,
    build_http_client,
    extract_slug,
    fetch_text,
    get_known_movie_mids,
    harvest_public_user,
    load_user_specs,
    normalize_profile_url,
    parse_profile_page,
    upsert_bundle_to_db,
)

PUBLIC_USER_PREFIX = "douban_public"
CATEGORY_CHOICES = ("too_light", "light_native", "medium_native", "heavy_capped")

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


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _default_output_dir() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(Path("reports") / "public_growth_runs" / stamp)


def _load_cookie_map(path: str | None) -> dict[str, str] | None:
    if not path:
        return None
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    if isinstance(raw, list):
        cookie_map: dict[str, str] = {}
        for item in raw:
            if isinstance(item, dict) and item.get("name") and item.get("value"):
                cookie_map[str(item["name"])] = str(item["value"])
        return cookie_map or None
    raise ValueError("cookies 文件必须是 JSON 对象或 cookie 数组")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _public_username_pattern() -> str:
    return f"{PUBLIC_USER_PREFIX}_%"


def _load_existing_public_seed_specs() -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT username FROM users WHERE username LIKE %s ORDER BY id",
                (_public_username_pattern(),),
            )
            rows = cursor.fetchall()
    finally:
        conn.close()

    specs: list[dict] = []
    prefix = f"{PUBLIC_USER_PREFIX}_"
    for row in rows:
        username = str(row["username"])
        if not username.startswith(prefix):
            continue
        slug = username[len(prefix) :]
        if not slug:
            continue
        specs.append({"profile_url": normalize_profile_url(slug)})
    return specs


def _merge_seed_specs(*seed_groups: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for group in seed_groups:
        for item in group:
            slug = extract_slug(item["profile_url"])
            if slug in seen:
                continue
            merged.append({"profile_url": normalize_profile_url(slug)})
            seen.add(slug)
    return merged


def _load_seed_specs(seed_config: str | None) -> tuple[list[dict], set[str]]:
    db_seed_specs = _load_existing_public_seed_specs()
    config_seed_specs: list[dict] = []
    if seed_config:
        config_path = Path(seed_config)
        if not config_path.exists():
            raise FileNotFoundError(f"seed 配置文件不存在: {seed_config}")
        config_seed_specs = [
            {"profile_url": spec.profile_url}
            for spec in load_user_specs(str(config_path), [])
        ]
    merged = _merge_seed_specs(db_seed_specs, config_seed_specs)
    existing_public_slugs = {extract_slug(spec["profile_url"]) for spec in db_seed_specs}
    return merged, existing_public_slugs


def _count_eligible_public_users() -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS c
                FROM (
                    SELECT r.user_id
                    FROM user_movie_ratings r
                    JOIN users u ON u.id = r.user_id
                    WHERE u.username LIKE %s
                    GROUP BY r.user_id
                    HAVING COUNT(*) >= 3
                       AND SUM(CASE WHEN r.rating >= 3.5 THEN 1 ELSE 0 END) >= 2
                ) eligible
                """,
                (_public_username_pattern(),),
            )
            row = cursor.fetchone()
    finally:
        conn.close()
    return int((row or {}).get("c") or 0)


def _load_known_movie_mids() -> set[str]:
    conn = get_connection()
    try:
        return get_known_movie_mids(conn)
    finally:
        conn.close()


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


def _discover_candidates(
    *,
    client,
    seed_specs: list[dict],
    existing_public_slugs: set[str],
    contacts_page_limit: int,
    delay_seconds: float,
) -> tuple[list[dict], list[dict]]:
    discovered_by_slug: dict[str, dict] = {}
    errors: list[dict] = []
    seed_slugs = {extract_slug(spec["profile_url"]) for spec in seed_specs}

    for spec_index, spec in enumerate(seed_specs):
        owner_slug = extract_slug(spec["profile_url"])
        for page_index in range(max(contacts_page_limit, 1)):
            start = page_index * 45
            url = f"https://www.douban.com/people/{owner_slug}/contacts"
            if start:
                url += f"?start={start}"
            try:
                html_text = fetch_text(client, url)
            except Exception as exc:
                errors.append(
                    {
                        "slug": owner_slug,
                        "page": page_index + 1,
                        "url": url,
                        "error": str(exc),
                    }
                )
                print(f"{owner_slug} contacts page {page_index + 1}: error -> {exc}")
                break

            page_candidates = _extract_contacts_from_html(html_text, owner_slug)
            new_count = 0
            for row in page_candidates:
                slug = row["slug"]
                if slug in seed_slugs or slug in existing_public_slugs or slug in discovered_by_slug:
                    continue
                discovered_by_slug[slug] = row
                new_count += 1
            print(
                f"{owner_slug} contacts page {page_index + 1}: "
                f"{new_count} new / {len(page_candidates)} extracted"
            )

            has_more_requests = (
                page_index < max(contacts_page_limit, 1) - 1
                or spec_index < len(seed_specs) - 1
            )
            if delay_seconds > 0 and has_more_requests:
                time.sleep(delay_seconds)

    return sorted(discovered_by_slug.values(), key=lambda row: row["slug"]), errors


def _classify_candidate(profile: dict) -> dict:
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

    return {
        "slug": profile["slug"],
        "profile_url": normalize_profile_url(profile["slug"]),
        "display_name": profile.get("display_name"),
        "collect_total": collect_total,
        "wish_total": wish_total,
        "total_interactions": total_interactions,
        "category": category,
        "recommended_max_collect_items": max_collect,
        "recommended_max_wish_items": max_wish,
    }


def _screen_candidates(
    *,
    client,
    candidates: list[dict],
    delay_seconds: float,
) -> tuple[list[dict], list[dict]]:
    screened: list[dict] = []
    errors: list[dict] = []

    for index, candidate in enumerate(candidates):
        slug = candidate["slug"]
        try:
            profile_html = fetch_text(client, normalize_profile_url(slug))
            screened_candidate = _classify_candidate(parse_profile_page(profile_html, slug))
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
            screened_candidate["display_name"] = (
                screened_candidate.get("display_name") or candidate.get("display_name")
            )
            screened_candidate["discovered_from"] = candidate.get("discovered_from")
            screened.append(screened_candidate)
            print(
                f"{slug}: {screened_candidate['category']} "
                f"collect={screened_candidate['collect_total']} wish={screened_candidate['wish_total']} "
                f"cap=({screened_candidate['recommended_max_collect_items']},"
                f"{screened_candidate['recommended_max_wish_items']})"
            )

        if delay_seconds > 0 and index < len(candidates) - 1:
            time.sleep(delay_seconds)

    return screened, errors


def _sort_selected_candidates(candidates: list[dict]) -> list[dict]:
    return sorted(
        candidates,
        key=lambda row: (
            -int(row.get("collect_total") or 0),
            -int(row.get("wish_total") or 0),
            str(row.get("slug") or ""),
        ),
    )


def _apply_import_caps(
    candidate: dict,
    *,
    max_collect_items: int | None,
    max_wish_items: int | None,
) -> dict:
    payload = dict(candidate)
    collect_cap = payload.get("recommended_max_collect_items")
    wish_cap = payload.get("recommended_max_wish_items")

    if collect_cap is not None and max_collect_items is not None:
        collect_cap = min(int(collect_cap), int(max_collect_items))
    if wish_cap is not None and max_wish_items is not None:
        wish_cap = min(int(wish_cap), int(max_wish_items))

    payload["selected_max_collect_items"] = int(collect_cap) if collect_cap else None
    payload["selected_max_wish_items"] = int(wish_cap) if wish_cap else None
    return payload


def _select_candidates(
    screened_candidates: list[dict],
    *,
    candidate_categories: list[str],
    max_collect_items: int | None,
    max_wish_items: int | None,
) -> list[dict]:
    filtered = [
        row for row in screened_candidates
        if row.get("category") in set(candidate_categories)
    ]
    sorted_rows = _sort_selected_candidates(filtered)
    return [
        _apply_import_caps(
            row,
            max_collect_items=max_collect_items,
            max_wish_items=max_wish_items,
        )
        for row in sorted_rows
    ]


def _maybe_sleep_between_users(delay_seconds: float, slug: str, has_more: bool) -> None:
    if delay_seconds <= 0 or not has_more:
        return
    print(f"Cooling down after {slug}: sleep {delay_seconds:.1f}s before next user...")
    time.sleep(delay_seconds)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="扩充公开豆瓣用户直到达到离线评估目标。")
    parser.add_argument(
        "--target-eligible-users",
        type=int,
        default=500,
        help="目标：满足离线评估条件的公开豆瓣用户数。",
    )
    parser.add_argument(
        "--cookies-file",
        required=True,
        help="Douban 登录 cookies JSON 文件。",
    )
    parser.add_argument(
        "--seed-config",
        default=None,
        help="可选额外 seed 配置文件；默认只使用 DB 中现有 douban_public_* 用户。",
    )
    parser.add_argument(
        "--contacts-page-limit",
        type=int,
        default=2,
        help="每个 seed 抓取多少页 contacts。",
    )
    parser.add_argument(
        "--discover-delay-seconds",
        type=float,
        default=1.5,
        help="contacts 抓取间隔。",
    )
    parser.add_argument(
        "--screen-delay-seconds",
        type=float,
        default=1.0,
        help="profile 筛选间隔。",
    )
    parser.add_argument(
        "--import-delay-seconds",
        type=float,
        default=6.0,
        help="单个用户导入时 collect / wish 分页抓取间隔。",
    )
    parser.add_argument(
        "--between-users-seconds",
        type=float,
        default=90.0,
        help="用户与用户之间的冷却时间。",
    )
    parser.add_argument(
        "--max-collect-items",
        type=int,
        default=300,
        help="每个用户最多导入多少 collect。",
    )
    parser.add_argument(
        "--max-wish-items",
        type=int,
        default=120,
        help="每个用户最多导入多少 wish。",
    )
    parser.add_argument(
        "--candidate-categories",
        nargs="+",
        choices=CATEGORY_CHOICES,
        default=["medium_native"],
        help="允许进入导入阶段的候选分类。",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="输出目录；默认 reports/public_growth_runs/<timestamp>/。",
    )
    args = parser.parse_args(argv)
    if args.output_dir is None:
        args.output_dir = _default_output_dir()
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    seeds_path = output_dir / "seeds.json"
    discovered_path = output_dir / "discovered_candidates.json"
    screened_path = output_dir / "screened_candidates.json"
    selected_path = output_dir / "selected_candidates.json"
    import_results_path = output_dir / "import_results.json"
    summary_path = output_dir / "summary.json"

    started_at = _now_iso()
    exit_code = 0
    stop_reason = "failed"
    pool_initialized = False
    known_mids: set[str] = set()

    seeds: list[dict] = []
    discovered_candidates: list[dict] = []
    discover_errors: list[dict] = []
    screened_candidates: list[dict] = []
    screen_errors: list[dict] = []
    selected_candidates: list[dict] = []
    import_results: list[dict] = []

    eligible_before = 0
    eligible_after = 0

    try:
        init_pool()
        pool_initialized = True

        seeds, existing_public_slugs = _load_seed_specs(args.seed_config)
        eligible_before = _count_eligible_public_users()
        eligible_after = eligible_before
        print(
            f"Current eligible public users: {eligible_before}/{args.target_eligible_users}"
        )
        print(f"Seed users: {len(seeds)}")

        if eligible_before >= args.target_eligible_users:
            stop_reason = "target_reached"
            print("Target already met. No expansion needed.")
        else:
            known_mids = _load_known_movie_mids()
            cookie_map = _load_cookie_map(args.cookies_file)

            with build_http_client(cookies=cookie_map) as client:
                discovered_candidates, discover_errors = _discover_candidates(
                    client=client,
                    seed_specs=seeds,
                    existing_public_slugs=existing_public_slugs,
                    contacts_page_limit=args.contacts_page_limit,
                    delay_seconds=args.discover_delay_seconds,
                )
                print(f"Discovered candidates: {len(discovered_candidates)}")

                screened_candidates, screen_errors = _screen_candidates(
                    client=client,
                    candidates=discovered_candidates,
                    delay_seconds=args.screen_delay_seconds,
                )
                print(f"Screened candidates: {len(screened_candidates)}")

                selected_candidates = _select_candidates(
                    screened_candidates,
                    candidate_categories=args.candidate_categories,
                    max_collect_items=args.max_collect_items,
                    max_wish_items=args.max_wish_items,
                )
                print(f"Selected candidates: {len(selected_candidates)}")

                if not selected_candidates:
                    stop_reason = "candidate_exhausted"
                    print("No candidates left after screening and category filtering.")
                else:
                    for index, candidate in enumerate(selected_candidates):
                        has_more = index < len(selected_candidates) - 1
                        slug = candidate["slug"]
                        try:
                            bundle = harvest_public_user(
                                client=client,
                                spec=DoubanUserSpec(profile_url=candidate["profile_url"]),
                                delay_seconds=args.import_delay_seconds,
                                page_limit=None,
                                max_collect_items=candidate["selected_max_collect_items"],
                                max_wish_items=candidate["selected_max_wish_items"],
                            )
                            conn = get_connection()
                            try:
                                db_result = upsert_bundle_to_db(
                                    conn,
                                    bundle,
                                    known_mids=known_mids,
                                )
                            finally:
                                conn.close()

                            eligible_after = _count_eligible_public_users()
                            result = {
                                "slug": slug,
                                "category": candidate["category"],
                                "collect_total": candidate["collect_total"],
                                "wish_total": candidate["wish_total"],
                                "selected_max_collect_items": candidate["selected_max_collect_items"],
                                "selected_max_wish_items": candidate["selected_max_wish_items"],
                                "status": "imported",
                                "db_result": db_result,
                                "eligible_users_after": eligible_after,
                            }
                            import_results.append(result)
                            print(
                                f"Imported {slug}: category={candidate['category']} "
                                f"collect={candidate['collect_total']} wish={candidate['wish_total']} "
                                f"user_id={db_result['user_id']} ratings={db_result['ratings_written']} "
                                f"prefs={db_result['prefs_written']} "
                                f"eligible={eligible_after}/{args.target_eligible_users}"
                            )
                            if eligible_after >= args.target_eligible_users:
                                stop_reason = "target_reached"
                                print("Target reached during import.")
                                break
                        except Exception as exc:
                            import_results.append(
                                {
                                    "slug": slug,
                                    "category": candidate["category"],
                                    "collect_total": candidate["collect_total"],
                                    "wish_total": candidate["wish_total"],
                                    "selected_max_collect_items": candidate["selected_max_collect_items"],
                                    "selected_max_wish_items": candidate["selected_max_wish_items"],
                                    "status": "failed",
                                    "error": str(exc),
                                }
                            )
                            print(
                                f"Failed {slug}: category={candidate['category']} "
                                f"collect={candidate['collect_total']} wish={candidate['wish_total']} "
                                f"error={exc}"
                            )
                        finally:
                            _write_json(
                                import_results_path,
                                {
                                    "generated_at": _now_iso(),
                                    "results": import_results,
                                },
                            )
                            if stop_reason != "target_reached":
                                _maybe_sleep_between_users(
                                    args.between_users_seconds,
                                    slug,
                                    has_more=has_more,
                                )

                    if stop_reason != "target_reached":
                        stop_reason = "candidate_exhausted"

    except Exception as exc:
        exit_code = 1
        stop_reason = "failed"
        print(f"Expansion run failed: {exc}")
    finally:
        if pool_initialized:
            try:
                close_pool()
            except Exception:
                pass

        failed_count = (
            len(discover_errors)
            + len(screen_errors)
            + sum(1 for row in import_results if row.get("status") == "failed")
        )
        imported_count = sum(1 for row in import_results if row.get("status") == "imported")

        _write_json(
            seeds_path,
            {
                "generated_at": _now_iso(),
                "seeds": seeds,
            },
        )
        _write_json(
            discovered_path,
            {
                "generated_at": _now_iso(),
                "candidates": discovered_candidates,
                "errors": discover_errors,
            },
        )
        _write_json(
            screened_path,
            {
                "generated_at": _now_iso(),
                "candidates": screened_candidates,
                "errors": screen_errors,
            },
        )
        _write_json(
            selected_path,
            {
                "generated_at": _now_iso(),
                "candidates": selected_candidates,
            },
        )
        _write_json(
            import_results_path,
            {
                "generated_at": _now_iso(),
                "results": import_results,
            },
        )
        summary = {
            "started_at": started_at,
            "finished_at": _now_iso(),
            "target_eligible_users": int(args.target_eligible_users),
            "eligible_users_before": int(eligible_before),
            "eligible_users_after": int(eligible_after),
            "seed_count": len(seeds),
            "discovered_count": len(discovered_candidates),
            "screened_count": len(screened_candidates),
            "selected_count": len(selected_candidates),
            "imported_count": imported_count,
            "failed_count": failed_count,
            "stop_reason": stop_reason,
        }
        _write_json(summary_path, summary)
        print(f"Stop reason: {stop_reason}")
        print(f"Summary written to: {summary_path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
