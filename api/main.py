from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError
from shared.db import Base, engine
from .routes import videos, clips, feedback, channels, analytics, autoposts, admin, health, alerts, approvals, slack, auth

app = FastAPI(title="Opus-like API")
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

try:
    Base.metadata.create_all(bind=engine)
except OperationalError:
    pass

app.include_router(videos.router, prefix="/videos", tags=["videos"])
app.include_router(clips.router, prefix="/clips", tags=["clips"])
app.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
    app.include_router(channels.router, prefix="/channels", tags=["channels"])
    app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
    app.include_router(autoposts.router, prefix="/autoposts", tags=["autoposts"])\n    app.include_router(admin.router, prefix="/admin", tags=["admin"])\n    app.include_router(health.router, tags=["health"])\n    app.include_router(alerts.router, prefix="/alerts", tags=["alerts"])\n    app.include_router(approvals.router, prefix="/approvals", tags=["approvals"])\n    app.include_router(slack.router, tags=["slack"])\n    app.include_router(auth.router, tags=["auth"])

app.mount("/static", StaticFiles(directory="/data"), name="static")
