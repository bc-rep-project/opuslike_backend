from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..deps import api_key_guard, get_db
from ..models import JobLog
from ..settings import settings
from redis import Redis
import json

router = APIRouter()

@router.get("/jobs", dependencies=[Depends(api_key_guard)])
def list_jobs(status: str = "error", limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(JobLog)
    if status:
        q = q.filter(JobLog.status == status)
    rows = q.order_by(JobLog.updated_at.desc()).limit(max(1, min(limit, 500))).all()
    return {"jobs": [{
        "id": r.id, "type": r.type, "status": r.status, "error": r.error,
        "attempts": r.attempts, "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        "payload": r.payload
    } for r in rows]}

class RetryBody(BaseModel):
    overwrite_type: str | None = None

@router.post("/jobs/{job_id}/retry", dependencies=[Depends(api_key_guard)])
def retry_job(job_id: str, body: RetryBody = RetryBody(), db: Session = Depends(get_db)):
    r = db.query(JobLog).filter_by(id=job_id).first()
    if not r: raise HTTPException(404, "job not found")
    payload = r.payload or {}
    if body.overwrite_type:
        payload["type"] = body.overwrite_type
    # enqueue
    rr = Redis.from_url(settings.REDIS_URL)
    rr.lpush("jobs", json.dumps(payload))
    # update attempts
    r.attempts = (r.attempts or 0) + 1
    r.status = "queued"
    db.commit()
    return {"ok": True}

@router.delete("/jobs/{job_id}", dependencies=[Depends(api_key_guard)])
def delete_job(job_id: str, db: Session = Depends(get_db)):
    r = db.query(JobLog).filter_by(id=job_id).first()
    if not r: raise HTTPException(404, "job not found")
    db.delete(r); db.commit()
    return {"ok": True}
