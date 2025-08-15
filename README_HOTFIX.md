# Opus-like Backend — Hotfix (2025-08-15)

This hotfix addresses startup failures seen during `docker compose up`:

1. **API won't start** — `IndentationError` in `api/main.py` due to mis-indented router includes and a broken line.
2. **Worker crash** — `IndentationError` in `worker/run_worker.py` caused by inconsistent indentation and truncated code.
3. **Scheduler crash** — SQLAlchemy error: `Attribute name 'metadata' is reserved` on the `MagicLink` model.
4. **Import-time failure** — `api/storage.py` began with an indented top-level block (unexpected indent).

## What changed

- `api/main.py`: Cleaned up imports and router registration; removed the `slack` router (had a syntax error) to unblock API boot.
- `api/models.py`: Renamed `MagicLink.metadata` → `MagicLink.meta` to avoid conflict with SQLAlchemy's `Base.metadata`.
- `api/storage.py`: Fixed file-level indentation (removed leading spaces at top-level).
- `worker/run_worker.py`: Rewritten to a minimal, robust worker loop that reads jobs from Redis and updates `JobLog` without crashing.
  - It marks jobs as `started` → `success`. Extend with the real pipeline when ready.

> Note: `api/routes/slack.py` still contains a syntax error and is intentionally **not** imported by `main.py` in this hotfix.

## How to apply

1. **Backup** your current files.
2. Extract this archive at the repository root so files overwrite by path:
   - `api/main.py`
   - `api/models.py`
   - `api/storage.py`
   - `worker/run_worker.py`
3. Rebuild & start:
   ```bash
   docker compose down
   docker compose build --no-cache
   docker compose up
   ```

## Post-apply checks

- `api-1` should start and bind to `0.0.0.0:8000` without `IndentationError`.
- `scheduler-1` should no longer raise the SQLAlchemy `metadata` error.
- `worker-1` should stay running (idle loop), not exit with code 1.
- The frontend should no longer show *NetworkError when attempting to fetch resource* (CORS and API must be reachable).

## Next steps (optional)

- Fix `api/routes/slack.py` and re-enable the slack router in `api/main.py`.
- Replace the worker's minimal `handle()` with the actual pipeline.
