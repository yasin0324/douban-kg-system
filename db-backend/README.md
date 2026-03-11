# db-backend

FastAPI backend for the Douban knowledge-graph project.

## Current scope

- Movie, person, graph, stats, auth, admin, and user-behavior APIs are active.
- User behavior remains available: likes, want-to-watch, and ratings.
- Recommendation APIs are active again with `content`, `item_cf`, `kg_path`, and `kg_embed` algorithms.
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
```

## Notes

- No Neo4j GDS plugin is required anymore.
- Recommendation embeddings are trained only from structural graph relations and intentionally ignore historical Neo4j `User` nodes or `RATED` edges.
- The evaluator writes the main multi-seed report to `reports/eval_results.json` and the single-seed appendix report to `reports/eval_results_legacy.json`.
