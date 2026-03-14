"""
Import public Douban movie interests into local JSON / MySQL.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import httpx
from lxml import html

from app.services.auth_service import hash_password


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DOUBAN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

RATING_CLASS_TO_VALUE = {
    "rating1-t": 1.0,
    "rating2-t": 2.0,
    "rating3-t": 3.0,
    "rating4-t": 4.0,
    "rating5-t": 5.0,
}
RATING_VALUE_TO_LABEL = {
    1.0: "很差",
    2.0: "较差",
    3.0: "还行",
    4.0: "推荐",
    5.0: "力荐",
}
RATING_LABEL_TO_VALUE = {label: value for value, label in RATING_VALUE_TO_LABEL.items()}
ACTION_PREFIX_TO_LIST = {
    "看过": "collect",
    "想看": "wish",
    "在看": "do",
}
MID_RE = re.compile(r"/subject/(\d+)/")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class DoubanUserSpec:
    profile_url: str
    import_username: str | None = None


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = WHITESPACE_RE.sub(" ", unescape(value)).strip()
    return cleaned or None


def extract_slug(profile_or_slug: str) -> str:
    if "://" not in profile_or_slug:
        return profile_or_slug.strip("/ ")
    parsed = urlparse(profile_or_slug)
    match = re.search(r"/people/([^/]+)/?", parsed.path)
    if not match:
        raise ValueError(f"无法从 URL 解析豆瓣用户 slug: {profile_or_slug}")
    return match.group(1)


def normalize_profile_url(profile_or_slug: str) -> str:
    slug = extract_slug(profile_or_slug)
    return f"https://www.douban.com/people/{slug}/"


def movie_list_url(slug: str, list_type: str, start: int = 0) -> str:
    return (
        f"https://movie.douban.com/people/{slug}/{list_type}"
        f"?sort=time&start={start}&filter=all&mode=list"
    )


def rss_url(slug: str) -> str:
    return f"https://www.douban.com/feed/people/{slug}/interests"


def build_http_client(
    timeout_seconds: float = 20.0,
    cookies: dict[str, str] | None = None,
) -> httpx.Client:
    return httpx.Client(
        headers=DOUBAN_HEADERS,
        cookies=cookies,
        follow_redirects=True,
        timeout=timeout_seconds,
    )


def _default_referer(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc == "movie.douban.com":
        return "https://movie.douban.com/"
    return "https://www.douban.com/"


def fetch_text(client: httpx.Client, url: str, max_retries: int = 5) -> str:
    last_error: Exception | None = None
    for attempt in range(max_retries):
        response = client.get(url, headers={"Referer": _default_referer(url)})
        if response.status_code < 400:
            response.encoding = response.encoding or "utf-8"
            return response.text

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if response.status_code not in {403, 429} or attempt == max_retries - 1:
                raise

            # Douban occasionally redirects aggressive pagination requests to sec.douban.com.
            time.sleep(10 * (attempt + 1))
            client.get(_default_referer(url))
            continue

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"无法获取页面: {url}")


def parse_profile_page(html_text: str, slug: str) -> dict[str, Any]:
    doc = html.fromstring(html_text)
    heading_texts = [clean_text(text) for text in doc.xpath("//h1//text()")]
    heading_texts = [text for text in heading_texts if text]
    display_name = heading_texts[0] if heading_texts else slug
    tagline = heading_texts[1] if len(heading_texts) > 1 else None
    page_text = doc.text_content()

    location_match = re.search(r"常居:\s*([^\s]+)", page_text)
    joined_match = re.search(r"(\d{4}-\d{2}-\d{2})加入", page_text)
    ip_match = re.search(r"IP属地：([^\s]+)", page_text)
    profile_id_match = re.search(r"(\d+)\s+\(" + re.escape(slug) + r"\)", page_text)

    movie_heading = clean_text(
        "".join(doc.xpath("//h2[contains(normalize-space(.), '的电影')]//text()"))
    )
    movie_counts = {
        "doing": _extract_count(movie_heading, "部在看"),
        "wish": _extract_count(movie_heading, "部想看"),
        "collect": _extract_count(movie_heading, "部看过"),
    }

    return {
        "slug": slug,
        "profile_url": normalize_profile_url(slug),
        "display_name": display_name,
        "tagline": tagline,
        "location": location_match.group(1) if location_match else None,
        "joined_at": joined_match.group(1) if joined_match else None,
        "ip_location": ip_match.group(1) if ip_match else None,
        "profile_id": profile_id_match.group(1) if profile_id_match else None,
        "movie_counts": movie_counts,
    }


def _extract_count(text: str | None, suffix: str) -> int | None:
    if not text:
        return None
    match = re.search(rf"(\d+){re.escape(suffix)}", text)
    return int(match.group(1)) if match else None


def parse_movie_list_page(html_text: str, list_type: str) -> dict[str, Any]:
    doc = html.fromstring(html_text)
    items: list[dict[str, Any]] = []

    for item_node in doc.xpath("//ul[contains(@class, 'list-view')]/li[contains(@class, 'item')]"):
        item_id = item_node.get("id", "")
        mid = item_id.replace("list", "", 1)

        title = clean_text("".join(item_node.xpath(".//div[@class='title']/a[1]//text()")))
        subject_url = clean_text(item_node.xpath("string(.//div[@class='title']/a[1]/@href)"))
        rating_class = clean_text(
            item_node.xpath("string(.//div[contains(@class, 'date')]//span[contains(@class, 'rating')]/@class)")
        )
        rating = RATING_CLASS_TO_VALUE.get(rating_class) if rating_class else None
        rating_label = RATING_VALUE_TO_LABEL.get(rating) if rating else None

        date_text = clean_text(item_node.xpath("string(.//div[contains(@class, 'item-show')]//div[@class='date'])"))
        date_match = DATE_RE.search(date_text or "")
        date_value = date_match.group(0) if date_match else None

        comment = clean_text(
            item_node.xpath("string(.//div[contains(@class, 'comment-item')]//div[contains(@class, 'comment')])")
        )
        if comment:
            comment = re.sub(r"\(\d+\s+有用\)\s*$", "", comment).strip()
            comment = clean_text(comment)

        intro = clean_text(
            item_node.xpath("string(.//div[contains(@class, 'comment-item')]//span[contains(@class, 'intro')])")
        )

        items.append(
            {
                "mid": mid,
                "title": title,
                "subject_url": subject_url,
                "list_type": list_type,
                "date": date_value,
                "rating": rating,
                "rating_label": rating_label,
                "comment_short": comment,
                "intro": intro,
                "source_cid": item_node.xpath("string(.//div[contains(@class, 'comment-item')]/@data-cid)") or None,
            }
        )

    total_pages = _parse_total_pages(doc)
    total_items = _parse_total_items(doc)
    return {
        "items": items,
        "total_pages": total_pages,
        "total_items": total_items,
    }


def _parse_total_pages(doc: html.HtmlElement) -> int:
    value = clean_text(
        doc.xpath(
            "string(//div[contains(@class, 'paginator')]//span[contains(@class, 'thispage')]/@data-total-page)"
        )
    )
    return int(value) if value else 1


def _parse_total_items(doc: html.HtmlElement) -> int | None:
    subject_num = clean_text(doc.xpath("string(//span[contains(@class, 'subject-num')])"))
    if not subject_num:
        return None
    match = re.search(r"/\s*(\d+)", subject_num)
    return int(match.group(1)) if match else None


def parse_interest_rss(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title"))
        link = clean_text(item.findtext("link"))
        description = clean_text(item.findtext("description"))
        pub_date = clean_text(item.findtext("pubDate"))
        guid = clean_text(item.findtext("guid"))
        if not title or not link:
            continue

        mid_match = MID_RE.search(link)
        if not mid_match or "movie.douban.com" not in link:
            continue

        action = None
        for prefix, list_type in ACTION_PREFIX_TO_LIST.items():
            if title.startswith(prefix):
                action = list_type
                break
        if action is None:
            continue

        rating_label = None
        rating_match = re.search(r"推荐:\s*([^<]+)", description or "")
        if rating_match:
            rating_label = clean_text(rating_match.group(1))

        comment = None
        comment_match = re.search(r"备注:\s*([^<]+)", description or "")
        if comment_match:
            comment = clean_text(comment_match.group(1))

        event_at = None
        if pub_date:
            parsed = parsedate_to_datetime(pub_date)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            event_at = parsed.astimezone(SHANGHAI_TZ).replace(tzinfo=None).isoformat(sep=" ")

        items.append(
            {
                "mid": mid_match.group(1),
                "action": action,
                "title": title,
                "subject_url": link,
                "rating_label": rating_label,
                "rating": RATING_LABEL_TO_VALUE.get(rating_label) if rating_label else None,
                "comment_short": comment,
                "event_at": event_at,
                "guid": guid,
            }
        )
    return items


def infer_local_datetime(date_str: str | None, slug: str, mid: str, list_type: str) -> str | None:
    if not date_str:
        return None
    base = datetime.strptime(date_str, "%Y-%m-%d")
    digest = hashlib.sha256(f"{slug}:{mid}:{list_type}:{date_str}".encode("utf-8")).hexdigest()
    seed = int(digest[:8], 16)

    if list_type == "wish":
        hour = 18 + seed % 5
    elif list_type == "collect":
        hour = 19 + seed % 5
    else:
        hour = 17 + seed % 6
    minute = seed % 60
    second = (seed // 60) % 60
    return base.replace(hour=hour, minute=minute, second=second).isoformat(sep=" ")


def merge_movie_items(slug: str, collect_items: list[dict[str, Any]], wish_items: list[dict[str, Any]], rss_items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    rss_by_key = {(item["action"], item["mid"]): item for item in rss_items}

    def merge_item(item: dict[str, Any]) -> dict[str, Any]:
        merged = dict(item)
        rss_item = rss_by_key.get((item["list_type"], item["mid"]))
        if rss_item:
            merged["rating"] = merged["rating"] if merged.get("rating") is not None else rss_item.get("rating")
            merged["rating_label"] = merged["rating_label"] or rss_item.get("rating_label")
            merged["comment_short"] = merged["comment_short"] or rss_item.get("comment_short")
            merged["event_at"] = rss_item.get("event_at") or infer_local_datetime(item.get("date"), slug, item["mid"], item["list_type"])
            merged["timestamp_precision"] = "datetime" if rss_item.get("event_at") else "date_inferred_time"
            merged["rss_guid"] = rss_item.get("guid")
        else:
            merged["event_at"] = infer_local_datetime(item.get("date"), slug, item["mid"], item["list_type"])
            merged["timestamp_precision"] = "date_inferred_time"
            merged["rss_guid"] = None
        return merged

    return {
        "collect": [merge_item(item) for item in collect_items],
        "wish": [merge_item(item) for item in wish_items],
        "do": [item for item in rss_items if item["action"] == "do"],
    }


def build_local_username(slug: str, override: str | None = None, prefix: str = "douban_public") -> str:
    return override or f"{prefix}_{slug}"


def build_import_preview(
    slug: str,
    merged_items: dict[str, list[dict[str, Any]]],
    import_username: str | None = None,
    derive_like_threshold: float = 4.5,
) -> dict[str, Any]:
    local_username = build_local_username(slug, import_username)
    ratings = []
    prefs = []

    for item in merged_items["collect"]:
        if item.get("rating") is None:
            continue
        ratings.append(
            {
                "mid": item["mid"],
                "rating": float(item["rating"]),
                "comment_short": item.get("comment_short"),
                "rated_at": item.get("event_at"),
            }
        )
        if float(item["rating"]) >= derive_like_threshold:
            prefs.append(
                {
                    "mid": item["mid"],
                    "pref_type": "like",
                    "created_at": item.get("event_at"),
                }
            )

    for item in merged_items["wish"]:
        prefs.append(
            {
                "mid": item["mid"],
                "pref_type": "want_to_watch",
                "created_at": item.get("event_at"),
            }
        )

    return {
        "local_username": local_username,
        "ratings": ratings,
        "prefs": prefs,
    }


def load_user_specs(config_path: str | None, cli_values: list[str]) -> list[DoubanUserSpec]:
    specs: list[DoubanUserSpec] = []
    if config_path:
        config_file = Path(config_path)
        if config_file.exists():
            raw_config = json.loads(config_file.read_text(encoding="utf-8"))
            if isinstance(raw_config, dict):
                for key in ("candidates", "users", "items"):
                    if isinstance(raw_config.get(key), list):
                        raw_config = raw_config[key]
                        break
            if not isinstance(raw_config, list):
                raise ValueError("配置文件必须是 JSON 数组，或包含 candidates/users/items 数组的对象")
            for item in raw_config:
                if isinstance(item, str):
                    specs.append(DoubanUserSpec(profile_url=item))
                elif isinstance(item, dict) and item.get("profile_url"):
                    specs.append(
                        DoubanUserSpec(
                            profile_url=item["profile_url"],
                            import_username=item.get("import_username"),
                        )
                    )
                else:
                    raise ValueError("配置项必须是 URL 字符串或包含 profile_url 的对象")

    for value in cli_values:
        specs.append(DoubanUserSpec(profile_url=value))

    unique_specs: list[DoubanUserSpec] = []
    seen: set[str] = set()
    for spec in specs:
        slug = extract_slug(spec.profile_url)
        if slug in seen:
            continue
        unique_specs.append(spec)
        seen.add(slug)

    return unique_specs


def harvest_public_user(
    client: httpx.Client,
    spec: DoubanUserSpec,
    delay_seconds: float = 1.0,
    page_limit: int | None = None,
    max_collect_items: int | None = None,
    max_wish_items: int | None = None,
    derive_like_threshold: float = 4.5,
) -> dict[str, Any]:
    slug = extract_slug(spec.profile_url)
    profile_html = fetch_text(client, normalize_profile_url(slug))
    profile = parse_profile_page(profile_html, slug)

    collect_items = _fetch_movie_items(
        client,
        slug,
        "collect",
        delay_seconds,
        page_limit,
        max_items=max_collect_items,
    )
    wish_items = _fetch_movie_items(
        client,
        slug,
        "wish",
        delay_seconds,
        page_limit,
        max_items=max_wish_items,
    )
    rss_items = parse_interest_rss(fetch_text(client, rss_url(slug)))
    merged_items = merge_movie_items(slug, collect_items["items"], wish_items["items"], rss_items)
    preview = build_import_preview(
        slug,
        merged_items,
        import_username=spec.import_username,
        derive_like_threshold=derive_like_threshold,
    )

    return {
        "source": {
            "fetched_at": datetime.now(SHANGHAI_TZ).replace(tzinfo=None).isoformat(sep=" "),
            "profile_url": normalize_profile_url(slug),
            "rss_url": rss_url(slug),
        },
        "profile": profile,
        "movie_collect": merged_items["collect"],
        "movie_wish": merged_items["wish"],
        "rss_recent": rss_items,
        "import_preview": preview,
        "summary": {
            "collect_count": len(merged_items["collect"]),
            "wish_count": len(merged_items["wish"]),
            "rating_count": len(preview["ratings"]),
            "pref_count": len(preview["prefs"]),
            "collect_total_items": collect_items["total_items"],
            "wish_total_items": wish_items["total_items"],
            "collect_total_pages": collect_items["total_pages"],
            "wish_total_pages": wish_items["total_pages"],
            "collect_fetched_pages": collect_items["fetched_pages"],
            "wish_fetched_pages": wish_items["fetched_pages"],
            "collect_max_items": collect_items["max_items"],
            "wish_max_items": wish_items["max_items"],
            "collect_capped": collect_items["capped"],
            "wish_capped": wish_items["capped"],
        },
    }


def _fetch_movie_items(
    client: httpx.Client,
    slug: str,
    list_type: str,
    delay_seconds: float,
    page_limit: int | None,
    max_items: int | None = None,
) -> dict[str, Any]:
    first_page = parse_movie_list_page(fetch_text(client, movie_list_url(slug, list_type, 0)), list_type)
    items = list(first_page["items"])
    capped = False
    if max_items is not None and max_items >= 0 and len(items) >= max_items:
        items = items[:max_items]
        capped = True
    total_pages = first_page["total_pages"]
    max_pages = min(total_pages, page_limit) if page_limit else total_pages

    fetched_pages = 1
    for page_number in range(2, max_pages + 1):
        if capped:
            break
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        start = (page_number - 1) * 30
        page_data = parse_movie_list_page(fetch_text(client, movie_list_url(slug, list_type, start)), list_type)
        items.extend(page_data["items"])
        fetched_pages = page_number
        if max_items is not None and max_items >= 0 and len(items) >= max_items:
            items = items[:max_items]
            capped = True
            break

    return {
        "items": items,
        "total_items": first_page["total_items"],
        "total_pages": total_pages,
        "fetched_pages": fetched_pages,
        "max_items": max_items,
        "capped": capped,
    }


def get_known_movie_mids(conn) -> set[str]:
    with conn.cursor() as cursor:
        cursor.execute("SELECT douban_id FROM movies WHERE douban_id IS NOT NULL")
        return {str(row["douban_id"]) for row in cursor.fetchall()}


def users_table_has_is_mock(conn) -> bool:
    with conn.cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM users LIKE 'is_mock'")
        return cursor.fetchone() is not None


def build_db_payload(bundle: dict[str, Any], known_mids: set[str] | None = None) -> dict[str, Any]:
    preview = bundle["import_preview"]
    ratings = preview["ratings"]
    prefs = preview["prefs"]

    if known_mids is not None:
        ratings = [row for row in ratings if row["mid"] in known_mids]
        prefs = [row for row in prefs if row["mid"] in known_mids]

    rating_mids = {row["mid"] for row in ratings}
    prefs = [row for row in prefs if row["mid"] not in rating_mids or row["pref_type"] != "want_to_watch"]

    return {
        "local_username": preview["local_username"],
        "nickname": bundle["profile"].get("display_name"),
        "ratings": ratings,
        "prefs": prefs,
    }


def upsert_bundle_to_db(conn, bundle: dict[str, Any], known_mids: set[str] | None = None) -> dict[str, Any]:
    payload = build_db_payload(bundle, known_mids=known_mids)
    has_is_mock = users_table_has_is_mock(conn)
    user_id = _upsert_user(
        conn,
        username=payload["local_username"],
        nickname=payload["nickname"],
        is_mock=resolve_imported_user_is_mock(has_is_mock),
    )

    _sync_ratings(conn, user_id, payload["ratings"])
    _sync_prefs(conn, user_id, payload["prefs"])

    return {
        "user_id": user_id,
        "username": payload["local_username"],
        "ratings_written": len(payload["ratings"]),
        "prefs_written": len(payload["prefs"]),
    }


def resolve_imported_user_is_mock(has_is_mock: bool) -> bool | None:
    if not has_is_mock:
        return None
    return False


def _upsert_user(conn, username: str, nickname: str | None, is_mock: bool | None) -> int:
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        existing = cursor.fetchone()
        if existing:
            if is_mock is None:
                cursor.execute(
                    "UPDATE users SET nickname = %s, updated_at = NOW() WHERE id = %s",
                    (nickname, existing["id"]),
                )
            else:
                cursor.execute(
                    "UPDATE users SET nickname = %s, is_mock = %s, updated_at = NOW() WHERE id = %s",
                    (nickname, 1 if is_mock else 0, existing["id"]),
                )
            conn.commit()
            return int(existing["id"])

        password_hash = hash_password(f"imported-public-user::{username}::{secrets.token_hex(8)}")
        if is_mock is None:
            cursor.execute(
                "INSERT INTO users (username, password_hash, nickname) VALUES (%s, %s, %s)",
                (username, password_hash, nickname),
            )
        else:
            cursor.execute(
                "INSERT INTO users (username, password_hash, nickname, is_mock) VALUES (%s, %s, %s, %s)",
                (username, password_hash, nickname, 1 if is_mock else 0),
            )
        conn.commit()
        return int(cursor.lastrowid)


def _sync_ratings(conn, user_id: int, ratings: list[dict[str, Any]]) -> None:
    incoming_mids = {row["mid"] for row in ratings}
    with conn.cursor() as cursor:
        cursor.execute("SELECT mid FROM user_movie_ratings WHERE user_id = %s", (user_id,))
        existing_mids = {str(row["mid"]) for row in cursor.fetchall()}
        stale_mids = existing_mids - incoming_mids
        if stale_mids:
            placeholders = ", ".join(["%s"] * len(stale_mids))
            cursor.execute(
                f"DELETE FROM user_movie_ratings WHERE user_id = %s AND mid IN ({placeholders})",
                [user_id, *sorted(stale_mids)],
            )

        for row in ratings:
            cursor.execute(
                "INSERT INTO user_movie_ratings (user_id, mid, rating, comment_short, rated_at) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE "
                "rating = VALUES(rating), "
                "comment_short = VALUES(comment_short), "
                "rated_at = VALUES(rated_at), "
                "updated_at = NOW()",
                (
                    user_id,
                    row["mid"],
                    row["rating"],
                    row.get("comment_short"),
                    row.get("rated_at"),
                ),
            )
        conn.commit()


def _sync_prefs(conn, user_id: int, prefs: list[dict[str, Any]]) -> None:
    incoming_mids = {row["mid"] for row in prefs}
    with conn.cursor() as cursor:
        cursor.execute("SELECT mid FROM user_movie_prefs WHERE user_id = %s", (user_id,))
        existing_mids = {str(row["mid"]) for row in cursor.fetchall()}
        stale_mids = existing_mids - incoming_mids
        if stale_mids:
            placeholders = ", ".join(["%s"] * len(stale_mids))
            cursor.execute(
                f"DELETE FROM user_movie_prefs WHERE user_id = %s AND mid IN ({placeholders})",
                [user_id, *sorted(stale_mids)],
            )

        for row in prefs:
            cursor.execute(
                "INSERT INTO user_movie_prefs (user_id, mid, pref_type, created_at) "
                "VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE "
                "pref_type = VALUES(pref_type), "
                "created_at = VALUES(created_at), "
                "updated_at = NOW()",
                (
                    user_id,
                    row["mid"],
                    row["pref_type"],
                    row.get("created_at"),
                ),
            )
        conn.commit()
