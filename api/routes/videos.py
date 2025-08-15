import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, HttpUrl
from redis import Redis
from sqlalchemy.orm import Session
from ..deps import api_key_guard, get_db
from ..settings import settings
from ..models import Video, Segment

router = APIRouter()

class CreateVideo(BaseModel):
    youtube_url: HttpUrl

@router.get("", dependencies=[Depends(api_key_guard)])
def list_videos(db: Session = Depends(get_db), limit: int = Query(20, ge=1, le=100)):
    rows = (db.query(Video).order_by(Video.created_at.desc()).limit(limit).all())
    return {"videos": [{
        "id": v.id,
        "youtube_url": v.youtube_url,
        "status": v.status,
        "created_at": v.created_at.isoformat() if v.created_at else None
    } for v in rows]}

@router.post("", dependencies=[Depends(api_key_guard)], status_code=201)
def create_video(payload: CreateVideo, db: Session = Depends(get_db)):
    video = Video(youtube_url=str(payload.youtube_url), status="queued")
    db.add(video)
    db.commit()
    db.refresh(video)
    r = Redis.from_url(settings.REDIS_URL)
    r.lpush("jobs", f'{{"type":"INGEST","video_id":"{video.id}","youtube_url":"{video.youtube_url}"}}')
    return {"video_id": video.id, "jobs": ["INGEST"]}

@router.get("/{video_id}", dependencies=[Depends(api_key_guard)])
def get_video(video_id: str, db: Session = Depends(get_db)):
    v = db.query(Video).filter(Video.id == video_id).first()
    if not v:
        raise HTTPException(404, "video not found")
    return {"video_id": v.id, "youtube_url": v.youtube_url, "status": v.status, "created_at": v.created_at.isoformat() if v.created_at else None}

@router.get("/{video_id}/moments", dependencies=[Depends(api_key_guard)])
def list_moments(video_id: str, limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    rows = (db.query(Segment).filter(Segment.video_id == video_id).order_by(Segment.score.desc().nullslast()).limit(limit).all())
    return {"video_id": video_id, "moments": [{
        "segment_id": s.id, "start": s.t_start, "end": s.t_end, "score": s.score, "reason": s.reason or {}
    } for s in rows]}

from ..models import Transcript
from ..settings import settings
from ..deps import api_key_guard
from ..models import Video
from fastapi import Body

@router.post("/{video_id}/titles", dependencies=[Depends(api_key_guard)])
def suggest_titles(video_id: str, db: Session = Depends(get_db), use_llm: bool = Body(False)):
    v = db.query(Video).filter_by(id=video_id).first()
    if not v: raise HTTPException(404, "video not found")
    t = db.query(Transcript).filter_by(video_id=video_id).order_by(Transcript.created_at.desc()).first()
    text = t.text if t and t.text else ""
    from ...nlp.titles import suggest_titles as _sug
    ideas = _sug(text, extra_context=v.title or "", use_llm=use_llm)
    v.title_suggestions = ideas
    db.commit()
    return {"video_id": video_id, "suggestions": ideas}
