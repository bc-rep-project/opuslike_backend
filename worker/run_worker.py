import os
import json
import time
from typing import Iterator, Dict, Any

from redis import Redis
from shared.db import SessionLocal
from api.models import JobLog

# Redis connection
r = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))

def with_db() -> Iterator[SessionLocal]:
    """Yield a database session and always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def update_log(log_id: str, **updates):
    if not log_id:
        return
    for db in with_db():
        jl = db.query(JobLog).filter_by(id=log_id).first()
        if jl:
            for k, v in updates.items():
                setattr(jl, k, v)
            db.commit()

def handle(job: Dict[str, Any]) -> None:
    """Minimal handler. Marks logs as success so the pipeline won't crash during bring-up.
    Extend this with real steps (download/transcribe/render) once the system is healthy.
    """
    log_id = job.get("log_id")
    update_log(log_id, status="started")
    # TODO: integrate real pipeline here
    # For now, just acknowledge the job without heavy processing.
    update_log(log_id, status="success")

def main() -> None:
    queue = os.getenv("JOBS_QUEUE", "jobs")
    while True:
        try:
            item = r.blpop(queue, timeout=5)
            if not item:
                continue
            _, raw = item
            try:
                job = json.loads(raw)
            except Exception:
                job = {"raw": raw.decode("utf-8", errors="ignore")}
            try:
                handle(job)
            except Exception as e:
                log_id = job.get("log_id") if isinstance(job, dict) else None
                update_log(log_id, status="error", error=str(e))
        except Exception as outer:
            # Last resort: don't crash the worker loop
            time.sleep(1)

if __name__ == "__main__":
    main()
