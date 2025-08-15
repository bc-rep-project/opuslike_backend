import os, time
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from redis import Redis
from prometheus_client import CollectorRegistry, Gauge, generate_latest, CONTENT_TYPE_LATEST

from ..deps import get_db
from ..settings import settings
from ..models import Video, Clip

router = APIRouter()
_start = time.time()

def _check_db(db: Session) -> tuple[bool, str|None]:
    try:
        db.execute("SELECT 1")
        return True, None
    except Exception as e:
        return False, str(e)

def _check_redis() -> tuple[bool, int, str|None]:
    try:
        r = Redis.from_url(settings.REDIS_URL)
        ok = bool(r.ping())
        qlen = int(r.llen("jobs"))
        return ok, qlen, None
    except Exception as e:
        return False, 0, str(e)

def _check_storage() -> tuple[bool, dict]:
    root = os.getenv("MEDIA_ROOT", "/data")
    ok = os.path.isdir(root) and os.access(root, os.W_OK)
    return ok, {"media_root": root}

@router.get("/health")
def health(db: Session = Depends(get_db)):
    db_ok, db_err = _check_db(db)
    r_ok, qlen, r_err = _check_redis()
    s_ok, s_info = _check_storage()
    ok = db_ok and r_ok and s_ok
    status = "ok" if ok else "degraded"
    return {
        "status": status,
        "uptime_sec": int(time.time() - _start),
        "checks": {
            "db": {"ok": db_ok, "error": db_err},
            "redis": {"ok": r_ok, "queue_len": qlen, "error": r_err},
            "storage": {"ok": s_ok, **s_info},
        }
    }

@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    reg = CollectorRegistry()
    g_db = Gauge("app_db_ok", "Database reachable (1/0)", registry=reg)
    g_redis = Gauge("app_redis_ok", "Redis reachable (1/0)", registry=reg)
    g_queue = Gauge("app_jobs_queue_length", "Length of Redis jobs queue", registry=reg)
    g_videos = Gauge("app_videos_total", "Total videos", registry=reg)
    g_clips = Gauge("app_clips_total", "Total clips", registry=reg)
    g_uptime = Gauge("app_uptime_seconds", "API process uptime (seconds)", registry=reg)

    db_ok, _ = _check_db(db)
    g_db.set(1 if db_ok else 0)

    try:
        g_videos.set(db.query(Video).count())
    except Exception:
        g_videos.set(0)
    try:
        g_clips.set(db.query(Clip).count())
    except Exception:
        g_clips.set(0)

    r_ok, qlen, _ = _check_redis()
    g_redis.set(1 if r_ok else 0)
    g_queue.set(qlen)

    g_uptime.set(time.time() - _start)

    output = generate_latest(reg)
    return Response(content=output, media_type=CONTENT_TYPE_LATEST)
