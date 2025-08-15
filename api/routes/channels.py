from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from redis import Redis
from ..deps import api_key_guard, get_db
from ..settings import settings
from ..models import ChannelSub, Video
from datetime import datetime

router = APIRouter()

class SubscribeBody(BaseModel):
    channel_id: str
    auto_render_top_k: int = 3
    daily_post_time: str | None = "08:00"  # UTC HH:MM
    keywords: list[str] | None = []

@router.post("/subscribe", dependencies=[Depends(api_key_guard)])
def subscribe(body: SubscribeBody, db: Session = Depends(get_db)):
    sub = db.query(ChannelSub).filter_by(channel_id=body.channel_id).first()
    if sub:
        sub.auto_render_top_k = body.auto_render_top_k
        sub.daily_post_time = body.daily_post_time
        sub.keywords = body.keywords
    else:
        sub = ChannelSub(channel_id=body.channel_id, auto_render_top_k=body.auto_render_top_k, daily_post_time=body.daily_post_time, keywords=body.keywords or [])
        db.add(sub)
    db.commit()
    return {"ok": True, "id": sub.id}

@router.get("", dependencies=[Depends(api_key_guard)])
def list_channels(db: Session = Depends(get_db)):
    rows = db.query(ChannelSub).all()
    def row(s: ChannelSub):
        return {
            "id": s.id, "channel_id": s.channel_id, "title": s.title,
            "last_published_at": s.last_published_at.isoformat() if s.last_published_at else None,
            "enabled": bool(s.enabled), "auto_render_top_k": s.auto_render_top_k,
            "daily_post_time": s.daily_post_time, "keywords": s.keywords or []
        }
    return {"channels": [row(s) for s in rows]}

@router.post("/sync_all", dependencies=[Depends(api_key_guard)])
def sync_all(db: Session = Depends(get_db)):
    r = Redis.from_url(settings.REDIS_URL)
    count = 0
    for s in db.query(ChannelSub).filter_by(enabled=1).all():
        r.lpush("jobs", '{"type":"SYNC_CHANNEL","channel_id":"%s"}' % s.channel_id)
        count += 1
    return {"queued": count}
