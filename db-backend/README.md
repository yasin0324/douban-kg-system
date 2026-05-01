# db-backend

FastAPI backend for the Douban knowledge-graph project.

## Current scope

- Movie, person, graph, stats, auth, admin, and user-behavior APIs are active.
- User behavior remains available: likes, want-to-watch, and ratings.
- Recommendation APIs are active again with `content`, `item_cf`, `kg_path`, `kg_embed`, and `cfkg` algorithms.
- Offline recommendation evaluation is available via `python -m app.algorithms.evaluator`.
- `/api/recommend/personal`, `/api/recommend/explain`, and `/api/recommend/evaluate` are backed by the current recommendation implementation.

## Requirements

- Python 3.11+
- `uv`
- MySQL 8.x
- Neo4j 5.x

## Quick start

```bash
cd db-backend
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
uv run python -m app.algorithms.evaluator
```

Health check:

- [http://localhost:8000/health](http://localhost:8000/health)
- [http://localhost:8000/docs](http://localhost:8000/docs)

## Database setup

Run the remaining migrations:

```bash
mysql -u root -p douban < migrations/001_create_user_tables.sql
mysql -u root -p douban < migrations/002_create_admin_tables.sql
mysql -u root -p douban < migrations/003_add_users_is_mock.sql
```

Import public Douban movie interests into JSON or MySQL:

```bash
uv run python scripts/discover_public_douban_candidates.py \
  --config app/seed/public_douban_users.json \
  --cookies-file /tmp/douban_cookies.json \
  --contacts-page-limit 1 \
  --output reports/public_douban_candidates.json
uv run python scripts/screen_public_douban_users.py \
  --config reports/public_douban_candidates.json \
  --cookies-file /tmp/douban_cookies.json \
  --output reports/public_douban_users_screened.json
uv run python scripts/import_public_douban_users.py --config app/seed/public_douban_users.json
uv run python scripts/import_public_douban_users.py --config app/seed/public_douban_users.json --write-db
uv run python scripts/import_public_douban_users.py \
  --config app/seed/public_douban_users_batch_02.json \
  --write-db \
  --delay-seconds 6.0 \
  --between-users-seconds 120 \
  --max-collect-items 300 \
  --max-wish-items 200 \
  --cookies-file /tmp/douban_cookies.json \
  --output reports/public_douban_users_full.json
```

Notes:

- `discover_public_douban_candidates.py` expands seed users through their public contacts pages and outputs deduplicated candidate profile URLs.
- `screen_public_douban_users.py` only requests profile pages and classifies candidates into `medium_native` / `heavy_capped` / `too_light`.
- The importer fetches all public `collect / wish` pages by default; use `--page-limit` only when you want a faster sample run.
- `--between-users-seconds` adds a cooldown between users, which is safer than running a long batch back-to-back against Douban.
- `--max-collect-items` / `--max-wish-items` let you cap heavy users and keep later imports closer to real medium-activity distributions.
- `want_to_watch` comes from Douban `wish`, and `like` is derived from public ratings `>= 4.5` by default. You can override this with `--like-threshold`.

## Notes

- No Neo4j GDS plugin is required anymore.
- KG-Embed can use structural graph relations and, in evaluation configurations, optional public-user positive rating triples.
- Formal thesis evidence should use `reports/eval_results_neg499.md`; historical and legacy reports are explained in `reports/README.md`.
