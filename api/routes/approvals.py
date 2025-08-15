from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..deps import api_key_guard, get_db
from ..models import Clip, Video, Transcript, Segment
from ..settings import settings
from datetime import datetime, timedelta
from ...nlp.titles import suggest_titles

router = APIRouter()

def _views_24h(m):
    s = (m or {}).get("youtube_timeseries") or []
    if len(s) < 2: return 0
    try:
        s_sorted = sorted(s, key=lambda x: x.get("date"))
        return max(0, int(s_sorted[-1].get("views",0)) - int(s_sorted[-2].get("views",0)))
    except Exception:
        return 0

@router.get("/pending", )
def pending(request: Request, db: Session = Depends(get_db), limit: int = 12):
    from .auth import check_magic
    if not (request.headers.get('x-api-key') or check_magic(request, db)):
        raise HTTPException(401, 'Unauthorized')
    rows = db.query(Clip).order_by(Clip.created_at.desc()).limit(200).all()
    items = []
    for c in rows:
        yt = (c.metrics or {}).get("youtube") or {}
        if yt.get("videoId"):
            continue  # already published
        v = db.query(Video).filter_by(id=c.video_id).first()
        if not v: continue
        sugg = v.title_suggestions or []
        if not sugg:
            t = db.query(Transcript).filter_by(video_id=v.id).order_by(Transcript.created_at.desc()).first()
            text = t.text if t and t.text else ""
            try:
                sugg = suggest_titles(text, extra_context=v.title or "", use_llm=False)
                v.title_suggestions = sugg; db.commit()
            except Exception:
                sugg = []
        items.append({
            "clip_id": c.id,
            "video_id": v.id,
            "video_title": v.title,
            "suggestions": sugg[:10],
            "thumbnail_url": c.thumbnail_url,
            "style_variants": c.style_variants or [],
            "status": c.status,
            "views_24h": _views_24h(c.metrics or {}),
            "storage_url": c.storage_url,
            "current_title": c.title or v.title or ""
        })
        if len(items) >= limit:
            break
    return {"items": items}

class ApproveBody(BaseModel):
    title: str
    style_key: str | None = None
    publish_youtube: bool = False
    privacyStatus: str = "unlisted"

@router.post("/{clip_id}/approve", )
def approve(clip_id: str, body: ApproveBody, db: Session = Depends(get_db)):
    c = db.query(Clip).filter_by(id=clip_id).first()
    if not c: raise HTTPException(404, "clip not found")
    c.title = body.title
    db.commit()
    # set style variant if provided
    if body.style_key:
        from .clips import set_style  # reuse internal logic? call directly is tricky; reimplement quick:
        variants = c.style_variants or []
        found = next((it for it in variants if it.get("key")==body.style_key), None)
        if found:
            c.thumbnail_path = found.get("path"); c.thumbnail_url = found.get("url"); db.commit()
    # optionally publish
    if body.publish_youtube:
        from redis import Redis
        from ..settings import settings
        r = Redis.from_url(settings.REDIS_URL)
        meta = {"title": body.title, "description": "", "tags": [], "privacyStatus": body.privacyStatus}
        r.lpush("jobs", __import__("json").dumps({"type":"UPLOAD_YT","clip_id": clip_id, "meta": meta}))
    return {"ok": True}
