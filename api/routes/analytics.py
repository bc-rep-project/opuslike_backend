from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..deps import api_key_guard, get_db
from ..models import Clip, Video
from datetime import datetime

router = APIRouter()

def _views_24h(m):
    s = (m or {}).get("youtube_timeseries") or []
    if len(s) < 2: return 0
    try:
        s_sorted = sorted(s, key=lambda x: x.get("date"))
        return max(0, int(s_sorted[-1].get("views",0)) - int(s_sorted[-2].get("views",0)))
    except Exception:
        return 0


def _impr_24h(m):
    s = (m or {}).get("youtube_timeseries") or []
    if not s: return 0
    try:
        s_sorted = sorted(s, key=lambda x: x.get("date"))
        # use last entry's impressions_day if available; otherwise diff of impressions if present
        last = s_sorted[-1]
        if "impressions_day" in last:
            return int(last.get("impressions_day", 0))
        if len(s_sorted) >= 2:
            prev = s_sorted[-2]
            return max(0, int(last.get("impressions", 0)) - int(prev.get("impressions", 0)))
    except Exception:
        pass
    return 0

@router.get("/leaderboard", dependencies=[Depends(api_key_guard)])
def leaderboard(db: Session = Depends(get_db), window_days: int = 1, limit: int = 10):
    # window_days currently unused; we compute daily delta from timeseries.
    rows = db.query(Clip).all()
    items = []
    for c in rows:
        vd = _views_24h(c.metrics or {})
        v = db.query(Video).filter_by(id=c.video_id).first()
        yt = (c.metrics or {}).get("youtube") or {}
        imp = _impr_24h(c.metrics or {})
        ctr = (vd / imp * 100.0) if imp > 0 else None
        item = {
            "clip_id": c.id,
            "title": (v.title if v and v.title else "Clip"),
            "views_24h": vd,
            "impressions_24h": imp,
            "ctr_proxy": ctr,
            "youtube_url": f"https://youtu.be/{yt['videoId']}" if yt.get("videoId") else None,
            "thumbnail_url": c.thumbnail_url,
            "storage_url": c.storage_url,
            "status": c.status,
        }
        items.append(item)
    items.sort(key=lambda x: x["views_24h"], reverse=True)
    return {"items": items[:max(1, min(limit, 50))]}
