from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from ..deps import get_db
from ..models import MagicLink

router = APIRouter()

class MagicBody(BaseModel):
    purpose: str = "approvals"
    ttl_minutes: int = 1440
    email: str | None = None
    metadata: dict | None = None

@router.post("/auth/magic")
def create_magic(body: MagicBody, db: Session = Depends(get_db)):
    import secrets
    tok = secrets.token_urlsafe(24)
    exp = datetime.now(timezone.utc) + timedelta(minutes=max(5, min(body.ttl_minutes, 60*24*14)))
    ml = MagicLink(token=tok, purpose=body.purpose, email=body.email, metadata=body.metadata, expires_at=exp)
    db.add(ml); db.commit(); db.refresh(ml)
    return {"token": tok, "expires_at": exp.isoformat()}

def check_magic(request: Request, db: Session) -> bool:
    hdr = request.headers.get("x-magic-token") or request.headers.get("X-Magic-Token")
    if not hdr: return False
    ml = db.query(MagicLink).filter_by(token=hdr).first()
    if not ml: return False
    if ml.used and ml.purpose != "approvals": return False
    now = datetime.now(timezone.utc)
    if ml.expires_at.tzinfo is None:
        # treat as UTC naive
        from datetime import timezone as _tz
        ml.expires_at = ml.expires_at.replace(tzinfo=_tz.utc)
    if ml.expires_at < now: return False
    return True
