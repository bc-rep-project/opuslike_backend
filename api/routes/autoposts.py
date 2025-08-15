from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..deps import api_key_guard, get_db
from ..models import AutoPost
from ..settings import settings
from redis import Redis
import json

router = APIRouter()

class AutoPostBody(BaseModel):
    platform: str  # 'webhook' or 'x'
    endpoint: str | None = None  # webhook URL if platform=webhook
    template: str = "{title} — {views_24h} views in 24h\n{url}"
    daily_time: str = "09:00"  # UTC HH:MM
    enabled: bool = True

@router.post("", dependencies=[Depends(api_key_guard)])
def create_autopost(body: AutoPostBody, db: Session = Depends(get_db)):
    ap = AutoPost(platform=body.platform, endpoint=body.endpoint, template=body.template, daily_time=body.daily_time, enabled=1 if body.enabled else 0)
    db.add(ap); db.commit(); db.refresh(ap)
    return {"id": ap.id}

@router.get("", dependencies=[Depends(api_key_guard)])
def list_autoposts(db: Session = Depends(get_db)):
    rows = db.query(AutoPost).all()
    return {"autoposts": [{"id": r.id, "platform": r.platform, "endpoint": r.endpoint, "template": r.template, "daily_time": r.daily_time, "enabled": bool(r.enabled)} for r in rows]}

@router.post("/{autopost_id}/run_now", dependencies=[Depends(api_key_guard)])
def run_now(autopost_id: str, db: Session = Depends(get_db)):
    ap = db.query(AutoPost).filter_by(id=autopost_id).first()
    if not ap: raise HTTPException(404, "not found")
    r = Redis.from_url(settings.REDIS_URL)
    r.lpush("jobs", json.dumps({"type":"AUTOPOST_FIRE","autopost_id": ap.id}))
    return {"queued": True}
