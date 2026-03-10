# db-backend

FastAPI backend for the Douban knowledge-graph project.

## Current scope

- Movie, person, graph, stats, auth, admin, and user-behavior APIs are active.
- User behavior remains available: likes, want-to-watch, and ratings.
- Recommendation algorithms, training scripts, evaluation reports, and GDS-based recommendation infrastructure have been removed.
- `/api/recommend/personal` and `/api/recommend/explain` remain as legacy compatibility stubs so the existing frontend recommendation UI degrades to an empty state instead of failing.

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
- No recommendation model warmup or recommendation dataset scripts remain in the backend.
- Existing historical Neo4j `User` nodes or `RATED` edges are ignored by the current backend.
