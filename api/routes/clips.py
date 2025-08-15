from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from redis import Redis
from ..deps import api_key_guard, get_db
from ..settings import settings
from ..models import Clip, Segment, Video
import json

router = APIRouter()

class RenderRequest(BaseModel):
    segment_ids: list[str]
    aspect_ratio: str = "9:16"
    caption_style: dict | None = None

@router.post("/{video_id}/render", dependencies=[Depends(api_key_guard)])
def render(video_id: str, payload: RenderRequest, db: Session = Depends(get_db)):
    v = db.query(Video).filter_by(id=video_id).first()
    if not v:
        raise HTTPException(404, "video not found")
    segs = db.query(Segment).filter(Segment.id.in_(payload.segment_ids)).all()
    if not segs:
        raise HTTPException(400, "no valid segments provided")

    r = Redis.from_url(settings.REDIS_URL)
    clip_ids = []
    for s in segs:
        clip = Clip(video_id=video_id, segment_id=s.id, aspect_ratio=payload.aspect_ratio, caption_style=payload.caption_style or {})
        db.add(clip)
        db.commit()
        db.refresh(clip)
        job = {"type":"RENDER","video_id": video_id,"clip_id": clip.id,"segment_id": s.id,"start": s.t_start,"end": s.t_end,"aspect_ratio": payload.aspect_ratio}
        r.lpush("jobs", json.dumps(job, separators=(',',':')))
        clip_ids.append(clip.id)
    return {"clip_ids": clip_ids}

@router.get("/{clip_id}", dependencies=[Depends(api_key_guard)])
def get_clip(clip_id: str, db: Session = Depends(get_db)):
    c = db.query(Clip).filter_by(id=clip_id).first()
    if not c:
        raise HTTPException(404, "clip not found")
    return {"clip_id": c.id, "status": c.status, "storage_url": c.storage_url, "output_path": c.output_path}

@router.get("/video/{video_id}", dependencies=[Depends(api_key_guard)])
def list_clips_for_video(video_id: str, db: Session = Depends(get_db)):
    rows = db.query(Clip).filter_by(video_id=video_id).all()
    return {"clips": [{"clip_id": c.id, "status": c.status, "storage_url": c.storage_url, "output_path": c.output_path} for c in rows]}

@router.get("/{clip_id}/signed_url", dependencies=[Depends(api_key_guard)])
def get_signed_url(clip_id: str, db: Session = Depends(get_db)):
    c = db.query(Clip).filter_by(id=clip_id).first()
    if not c:
        raise HTTPException(404, "clip not found")
    # If local, just return static URL
    if c.output_path and (c.output_path.startswith("/data/") or c.output_path.endswith(".mp4") and c.output_path.startswith("/")):
        return {"clip_id": c.id, "url": c.storage_url}
    # Cloud object: sign on demand
    from ..storage import sign_url
    if not c.output_path:
        raise HTTPException(400, "clip has no object path yet")
    url = sign_url(c.output_path, expires_seconds=3600)
    return {"clip_id": c.id, "url": url}


class PublishBody(BaseModel):
    title: str
    description: str | None = None
    tags: list[str] | None = []
    privacyStatus: str = "unlisted"

@router.post("/{clip_id}/publish/youtube", dependencies=[Depends(api_key_guard)])
def publish_youtube(clip_id: str, body: PublishBody, db: Session = Depends(get_db)):
    c = db.query(Clip).filter_by(id=clip_id).first()
    if not c:
        raise HTTPException(404, "clip not found")
    # enqueue upload job
    r = Redis.from_url(settings.REDIS_URL)
    r.lpush("jobs", __import__("json").dumps({"type":"UPLOAD_YT","clip_id": clip_id, "meta": {"title": body.title, "description": body.description or "", "tags": body.tags or [], "privacyStatus": body.privacyStatus}}))
    return {"ok": True, "job": "UPLOAD_YT"}


class ThumbBody(BaseModel):
    title: str | None = None
    aspect_ratio: str = "9:16"

@router.post("/{clip_id}/thumbnail", dependencies=[Depends(api_key_guard)])
def make_thumbnail(clip_id: str, body: ThumbBody, db: Session = Depends(get_db)):
    c = db.query(Clip).filter_by(id=clip_id).first()
    if not c: raise HTTPException(404, "clip not found")
    from ..models import Video, Segment
    v = db.query(Video).filter_by(id=c.video_id).first()
    s = db.query(Segment).filter_by(id=c.segment_id).first()
    if not (v and s): raise HTTPException(400, "clip missing video/segment")
    # generate now (sync) for simplicity
    base_dir = os.getenv("MEDIA_ROOT", "/data")
    os.makedirs(os.path.join(base_dir, "thumbnails"), exist_ok=True)
    out = os.path.join(base_dir, "thumbnails", f"{clip_id}.jpg")
    from ..settings import settings
    from ..deps import get_db as _
    from ...worker.pipeline import generate_thumbnail, compute_face_crop
    crop_hint = None
    try:
        crop_hint = compute_face_crop(v.source_path, s.t_start, s.t_end, target_h=1920, crop_w=1080) if body.aspect_ratio == "9:16" else None
    except Exception:
        crop_hint = None
    generate_thumbnail(v.source_path, s.t_start, s.t_end, out, body.aspect_ratio, crop_hint, body.title or "")
    c.thumbnail_path = out
    c.thumbnail_url = f"/static/thumbnails/{clip_id}.jpg"
    db.commit()
    return {"thumbnail_url": c.thumbnail_url}

class ABThumbsBody(BaseModel):
    title_a: str
    title_b: str
    aspect_ratio: str = "9:16"

@router.post("/{clip_id}/thumbnails/ab", dependencies=[Depends(api_key_guard)])
def ab_thumbs(clip_id: str, body: ABThumbsBody, db: Session = Depends(get_db)):
    c = db.query(Clip).filter_by(id=clip_id).first()
    if not c: raise HTTPException(404, "clip not found")
    from ..models import Video, Segment
    v = db.query(Video).filter_by(id=c.video_id).first()
    s = db.query(Segment).filter_by(id=c.segment_id).first()
    if not (v and s): raise HTTPException(400, "clip missing video/segment")
    # generate A & B
    base_dir = os.getenv("MEDIA_ROOT", "/data")
    os.makedirs(os.path.join(base_dir, "thumbnails"), exist_ok=True)
    a_path = os.path.join(base_dir, "thumbnails", f"{clip_id}_A.jpg")
    b_path = os.path.join(base_dir, "thumbnails", f"{clip_id}_B.jpg")
    from ...worker.pipeline import generate_thumbnail, compute_face_crop
    crop_hint = None
    try:
        crop_hint = compute_face_crop(v.source_path, s.t_start, s.t_end, target_h=1920, crop_w=1080) if body.aspect_ratio == "9:16" else None
    except Exception:
        crop_hint = None
    generate_thumbnail(v.source_path, s.t_start, s.t_end, a_path, body.aspect_ratio, crop_hint, body.title_a)
    generate_thumbnail(v.source_path, s.t_start, s.t_end, b_path, body.aspect_ratio, crop_hint, body.title_b)
    c.thumbnail_a_path = a_path; c.thumbnail_a_url = f"/static/thumbnails/{clip_id}_A.jpg"
    c.thumbnail_b_path = b_path; c.thumbnail_b_url = f"/static/thumbnails/{clip_id}_B.jpg"
    db.commit()
    return {"A": c.thumbnail_a_url, "B": c.thumbnail_b_url}

class ABStartBody(BaseModel):
    start: bool = True

@router.post("/{clip_id}/thumbnails/ab/start", dependencies=[Depends(api_key_guard)])
def ab_start(clip_id: str, body: ABStartBody, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    c = db.query(Clip).filter_by(id=clip_id).first()
    if not c: raise HTTPException(404, "clip not found")
    if not (c.thumbnail_a_path and c.thumbnail_b_path): raise HTTPException(400, "generate A/B thumbnails first")
    c.ab_status = "running" if body.start else "stopped"
    # default to A on start
    if body.start and not c.ab_active:
        c.ab_active = "A"
    hist = c.ab_history or []
    hist.append({"ts": datetime.now(timezone.utc).isoformat(), "event": "ab_" + ("start" if body.start else "stop"), "variant": c.ab_active})
    c.ab_history = hist
    db.commit()
    return {"ok": True, "ab_status": c.ab_status, "ab_active": c.ab_active}

class StylePackBody(BaseModel):
    title: str
    aspect_ratio: str = "9:16"

@router.post("/{clip_id}/thumbnails/styles", dependencies=[Depends(api_key_guard)])
def make_styles(clip_id: str, body: StylePackBody, db: Session = Depends(get_db)):
    c = db.query(Clip).filter_by(id=clip_id).first()
    if not c: raise HTTPException(404, "clip not found")
    from ..models import Video, Segment
    v = db.query(Video).filter_by(id=c.video_id).first()
    s = db.query(Segment).filter_by(id=c.segment_id).first()
    if not (v and s): raise HTTPException(400, "clip missing video/segment")
    base_dir = os.getenv("MEDIA_ROOT", "/data")
    os.makedirs(os.path.join(base_dir, "thumbnails"), exist_ok=True)
    from ...worker.pipeline import generate_thumbnail, compute_face_crop
    crop_hint = None
    try:
        crop_hint = compute_face_crop(v.source_path, s.t_start, s.t_end, target_h=1920, crop_w=1080) if body.aspect_ratio == "9:16" else None
    except Exception:
        crop_hint = None

    styles = [
        {"key":"S1","title": body.title, "uppercase": False, "emoji": ""},
        {"key":"S2","title": body.title.upper(), "uppercase": True, "emoji": "🔥"},
        {"key":"S3","title": "💡 " + body.title, "uppercase": False, "emoji": "💡"},
        {"key":"S4","title": body.title, "uppercase": False, "emoji": "🚀"},
    ]
    out_items = []
    for st in styles:
        out = os.path.join(base_dir, "thumbnails", f"{clip_id}_{st['key']}.jpg")
        # Reuse generate_thumbnail; store emoji in title if present
        generate_thumbnail(v.source_path, s.t_start, s.t_end, out, body.aspect_ratio, crop_hint, st["title"])
        out_items.append({"key": st["key"], "url": f"/static/thumbnails/{clip_id}_{st['key']}.jpg", "path": out, "style": st})
    c.style_variants = out_items
    db.commit()
    return {"variants": [{"key":it["key"], "url": it["url"]} for it in out_items]}

class SetStyleBody(BaseModel):
    key: str
    set_on_youtube: bool = True

@router.post("/{clip_id}/thumbnails/set", dependencies=[Depends(api_key_guard)])
def set_style(clip_id: str, body: SetStyleBody, db: Session = Depends(get_db)):
    c = db.query(Clip).filter_by(id=clip_id).first()
    if not c: raise HTTPException(404, "clip not found")
    variants = c.style_variants or []
    found = next((it for it in variants if it.get("key")==body.key), None)
    if not found: raise HTTPException(404, "style not found")
    c.thumbnail_path = found.get("path"); c.thumbnail_url = found.get("url")
    db.commit()
    if body.set_on_youtube:
        from redis import Redis
        from ..settings import settings
        r = Redis.from_url(settings.REDIS_URL)
        r.lpush("jobs", json.dumps({"type":"THUMB_SET_YT_PATH", "clip_id": clip_id, "image_path": found.get("path")}))
    return {"thumbnail_url": c.thumbnail_url}


class PublishTikTokBody(BaseModel):
    title: str

@router.post("/{clip_id}/publish/tiktok", dependencies=[Depends(api_key_guard)])
def publish_tiktok(clip_id: str, body: PublishTikTokBody, db: Session = Depends(get_db)):
    c = db.query(Clip).filter_by(id=clip_id).first()
    if not c: raise HTTPException(404, "clip not found")
    r = Redis.from_url(settings.REDIS_URL)
    r.lpush("jobs", __import__("json").dumps({"type":"UPLOAD_TT","clip_id": clip_id, "meta": {"title": body.title}}))
    return {"ok": True}


class TitleBody(BaseModel):
    title: str

@router.post("/{clip_id}/title", dependencies=[Depends(api_key_guard)])
def set_title(clip_id: str, body: TitleBody, db: Session = Depends(get_db)):
    c = db.query(Clip).filter_by(id=clip_id).first()
    if not c: raise HTTPException(404, "clip not found")
    c.title = body.title
    db.commit()
    return {"ok": True}
