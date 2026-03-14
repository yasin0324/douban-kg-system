from app.services.douban_public_import import (
    _fetch_movie_items,
    build_db_payload,
    build_import_preview,
    build_local_username,
    extract_slug,
    load_user_specs,
    merge_movie_items,
    parse_interest_rss,
    parse_movie_list_page,
    parse_profile_page,
    resolve_imported_user_is_mock,
)


PROFILE_HTML = """
<html><body>
  <h1>blacky <span>小黑屋里边儿请~</span></h1>
  <h2>blacky的电影 · · · · · · ( 49部想看 · 1459部看过 · 2个片单 )</h2>
  <div>常居: <a>北京</a> 1912712 (guanyinan) 2007-10-12加入 IP属地：北京</div>
</body></html>
"""


COLLECT_HTML = """
<html><body>
  <span class="subject-num">1-30 / 1459</span>
  <ul class="list-view">
    <li id="list1299536" class="item">
      <div class="item-show">
        <div class="title">
          <a href="https://movie.douban.com/subject/1299536/">不良少女莫妮卡 / Sommaren med Monika</a>
          <span class="playable">[可播放]</span>
        </div>
        <div class="date">
          <span class="rating4-t"></span>&nbsp;&nbsp;
          2026-03-08
        </div>
      </div>
      <div id="grid1299536" data-cid="4789325859" class="hide comment-item">
        <div class="grid-date">
          <span class="intro">1953-02-09 / 瑞典 / 剧情 / 爱情</span><br>
        </div>
      </div>
    </li>
    <li id="list36912889" class="item">
      <div class="item-show">
        <div class="title">
          <a href="https://movie.douban.com/subject/36912889/">嘎啦</a>
        </div>
        <div class="date">2026-03-07</div>
      </div>
      <div id="grid36912889" data-cid="4788113204" class="hide comment-item">
        <div class="grid-date">
          <span class="intro">2024-07-19(中国台湾) / 恐怖</span><br>
        </div>
        <div class="comment">
          大学生作业也不至于这样
        </div>
      </div>
    </li>
  </ul>
  <div class="paginator">
    <span class="thispage" data-total-page="49">1</span>
  </div>
</body></html>
"""


WISH_HTML = """
<html><body>
  <span class="subject-num">1-30 / 49</span>
  <ul class="list-view">
    <li id="list1294503" class="item">
      <div class="item-show">
        <div class="title">
          <a href="https://movie.douban.com/subject/1294503/">紫色 / The Color Purple</a>
        </div>
        <div class="date">2026-02-13</div>
      </div>
      <div id="grid1294503" data-cid="4700000000" class="hide comment-item"></div>
    </li>
  </ul>
  <div class="paginator">
    <span class="thispage" data-total-page="2">1</span>
  </div>
</body></html>
"""


RSS_XML = """
<rss version="2.0">
  <channel>
    <item>
      <title>看过钻石般的她</title>
      <link>https://movie.douban.com/subject/36968995/</link>
      <description><![CDATA[
        <table><tr><td><p>推荐: 力荐</p></td></tr></table>
      ]]></description>
      <pubDate>Fri, 06 Mar 2026 16:15:48 GMT</pubDate>
      <guid>https://www.douban.com/people/guanyinan/interests/4787671216</guid>
    </item>
    <item>
      <title>看过非穷尽列举</title>
      <link>https://movie.douban.com/subject/37293378/</link>
      <description><![CDATA[
        <table><tr><td><p>推荐: 力荐</p><p>备注: 每个女人都应该是女权主义者</p></td></tr></table>
      ]]></description>
      <pubDate>Sat, 28 Feb 2026 13:59:09 GMT</pubDate>
      <guid>https://www.douban.com/people/guanyinan/interests/4782938053</guid>
    </item>
    <item>
      <title>想看紫色</title>
      <link>https://movie.douban.com/subject/1294503/</link>
      <description><![CDATA[
        <table><tr><td></td></tr></table>
      ]]></description>
      <pubDate>Thu, 12 Feb 2026 12:00:00 GMT</pubDate>
      <guid>https://www.douban.com/people/guanyinan/interests/4700000000</guid>
    </item>
  </channel>
</rss>
"""


def test_extract_slug_accepts_full_url():
    assert extract_slug("https://www.douban.com/people/guanyinan/") == "guanyinan"


def test_parse_profile_page_extracts_core_fields():
    parsed = parse_profile_page(PROFILE_HTML, "guanyinan")

    assert parsed["display_name"] == "blacky"
    assert parsed["tagline"] == "小黑屋里边儿请~"
    assert parsed["location"] == "北京"
    assert parsed["joined_at"] == "2007-10-12"
    assert parsed["movie_counts"]["wish"] == 49
    assert parsed["movie_counts"]["collect"] == 1459


def test_parse_movie_list_page_extracts_rating_and_comment():
    parsed = parse_movie_list_page(COLLECT_HTML, "collect")

    assert parsed["total_pages"] == 49
    assert parsed["total_items"] == 1459
    assert parsed["items"][0]["mid"] == "1299536"
    assert parsed["items"][0]["rating"] == 4.0
    assert parsed["items"][0]["rating_label"] == "推荐"
    assert parsed["items"][1]["comment_short"] == "大学生作业也不至于这样"


def test_parse_interest_rss_extracts_action_rating_and_comment():
    parsed = parse_interest_rss(RSS_XML)

    assert parsed[0]["action"] == "collect"
    assert parsed[0]["rating"] == 5.0
    assert parsed[1]["comment_short"] == "每个女人都应该是女权主义者"
    assert parsed[2]["action"] == "wish"
    assert parsed[2]["event_at"] == "2026-02-12 20:00:00"


def test_merge_and_build_payload_filter_unknown_movies():
    collect_items = parse_movie_list_page(COLLECT_HTML, "collect")["items"]
    wish_items = parse_movie_list_page(WISH_HTML, "wish")["items"]
    rss_items = parse_interest_rss(RSS_XML)

    merged = merge_movie_items("guanyinan", collect_items, wish_items, rss_items)
    preview = build_import_preview("guanyinan", merged, import_username="douban_public_guanyinan")
    payload = build_db_payload(
        {
            "profile": parse_profile_page(PROFILE_HTML, "guanyinan"),
            "import_preview": preview,
        },
        known_mids={"1299536", "1294503"},
    )

    assert build_local_username("guanyinan", "douban_public_guanyinan") == "douban_public_guanyinan"
    assert payload["local_username"] == "douban_public_guanyinan"
    assert payload["ratings"] == [
        {
            "mid": "1299536",
            "rating": 4.0,
            "comment_short": None,
            "rated_at": preview["ratings"][0]["rated_at"],
        }
    ]
    assert payload["prefs"] == [
        {
            "mid": "1294503",
            "pref_type": "want_to_watch",
            "created_at": preview["prefs"][-1]["created_at"],
        }
    ]


def test_build_import_preview_uses_45_threshold_for_like_derivation():
    collect_items = parse_movie_list_page(COLLECT_HTML, "collect")["items"]
    wish_items = parse_movie_list_page(WISH_HTML, "wish")["items"]
    rss_items = parse_interest_rss(RSS_XML)

    merged = merge_movie_items("guanyinan", collect_items, wish_items, rss_items)
    preview = build_import_preview("guanyinan", merged)

    assert preview["ratings"][0]["rating"] == 4.0
    assert preview["prefs"] == [
        {
            "mid": "1294503",
            "pref_type": "want_to_watch",
            "created_at": preview["prefs"][0]["created_at"],
        }
    ]


def test_fetch_movie_items_stops_at_max_items(monkeypatch):
    pages = {
        0: {
            "items": [{"mid": str(idx)} for idx in range(30)],
            "total_pages": 3,
            "total_items": 70,
        },
        30: {
            "items": [{"mid": str(idx)} for idx in range(30, 60)],
            "total_pages": 3,
            "total_items": 70,
        },
        60: {
            "items": [{"mid": str(idx)} for idx in range(60, 70)],
            "total_pages": 3,
            "total_items": 70,
        },
    }

    def fake_fetch_text(client, url, max_retries=5):
        return url

    def fake_parse_movie_list_page(value, list_type):
        start = int(value.split("start=")[1].split("&")[0])
        return pages[start]

    monkeypatch.setattr("app.services.douban_public_import.fetch_text", fake_fetch_text)
    monkeypatch.setattr("app.services.douban_public_import.parse_movie_list_page", fake_parse_movie_list_page)

    parsed = _fetch_movie_items(
        client=None,
        slug="guanyinan",
        list_type="collect",
        delay_seconds=0.0,
        page_limit=None,
        max_items=35,
    )

    assert len(parsed["items"]) == 35
    assert parsed["items"][-1]["mid"] == "34"
    assert parsed["fetched_pages"] == 2
    assert parsed["capped"] is True


def test_load_user_specs_accepts_discovery_payload(tmp_path):
    config_path = tmp_path / "candidates.json"
    config_path.write_text(
        """
        {
          "candidates": [
            {"profile_url": "https://www.douban.com/people/alice/"},
            {"profile_url": "https://www.douban.com/people/bob/"}
          ]
        }
        """,
        encoding="utf-8",
    )

    specs = load_user_specs(str(config_path), [])

    assert [spec.profile_url for spec in specs] == [
        "https://www.douban.com/people/alice/",
        "https://www.douban.com/people/bob/",
    ]


def test_resolve_imported_user_is_mock_defaults_public_users_to_real():
    assert resolve_imported_user_is_mock(True) is False
    assert resolve_imported_user_is_mock(False) is None
