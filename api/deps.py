from fastapi import Header, HTTPException
from sqlalchemy.orm import Session
from .settings import settings
from shared.db import SessionLocal

async def api_key_guard(x_api_key: str = Header(None)):
    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
