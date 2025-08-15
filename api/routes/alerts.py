from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, AnyHttpUrl
from sqlalchemy.orm import Session
from ..deps import api_key_guard, get_db
from ..models import AlertChannel, AlertSettings
from ..settings import settings
import json
from redis import Redis

router = APIRouter()

class ChannelBody(BaseModel):
    kind: str  # 'slack' | 'webhook'
    endpoint: AnyHttpUrl
    enabled: bool = True

@router.post("/channels", dependencies=[Depends(api_key_guard)])
def add_channel(body: ChannelBody, db: Session = Depends(get_db)):
    ch = AlertChannel(kind=body.kind, endpoint=str(body.endpoint), enabled=1 if body.enabled else 0)
    db.add(ch); db.commit(); db.refresh(ch)
    return {"id": ch.id}

@router.get("/channels", dependencies=[Depends(api_key_guard)])
def list_channels(db: Session = Depends(get_db)):
    rows = db.query(AlertChannel).all()
    return {"channels": [{"id": r.id, "kind": r.kind, "endpoint": r.endpoint, "enabled": bool(r.enabled)} for r in rows]}

class SettingsBody(BaseModel):
    queue_threshold: int | None = None
    debounce_min: int | None = None
    health_enabled: bool | None = None

@router.get("/settings", dependencies=[Depends(api_key_guard)])
def get_settings(db: Session = Depends(get_db)):
    s = db.query(AlertSettings).first()
    if not s:
        s = AlertSettings(); db.add(s); db.commit(); db.refresh(s)
    return {"queue_threshold": s.queue_threshold, "debounce_min": s.debounce_min, "health_enabled": bool(s.health_enabled)}

@router.post("/settings", dependencies=[Depends(api_key_guard)])
def set_settings(body: SettingsBody, db: Session = Depends(get_db)):
    s = db.query(AlertSettings).first()
    if not s:
        s = AlertSettings(); db.add(s)
    if body.queue_threshold is not None: s.queue_threshold = body.queue_threshold
    if body.debounce_min is not None: s.debounce_min = body.debounce_min
    if body.health_enabled is not None: s.health_enabled = 1 if body.health_enabled else 0
    db.commit()
    return {"ok": True}

@router.post("/test", dependencies=[Depends(api_key_guard)])
def send_test(db: Session = Depends(get_db)):
    r = Redis.from_url(settings.REDIS_URL)
    r.lpush("jobs", json.dumps({"type":"ALERT_TEST"}))
    return {"queued": True}
