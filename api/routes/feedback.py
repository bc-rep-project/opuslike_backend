from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..deps import api_key_guard, get_db
from ..models import Segment, Clip

router = APIRouter()

class Feedback(BaseModel):
    segment_id: str | None = None
    clip_id: str | None = None
    label: str
    notes: str | None = None

@router.post("", dependencies=[Depends(api_key_guard)])
def submit_feedback(body: Feedback, db: Session = Depends(get_db)):
    # MVP: accept payload; you'd persist it here for training
    return {"ok": True}
