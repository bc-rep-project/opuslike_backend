import uuid, enum
from datetime import datetime
from sqlalchemy import Column, Text, Integer, Float, JSON, Enum, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from shared.db import Base

class JobType(str, enum.Enum):
    INGEST = "INGEST"
    TRANSCRIBE = "TRANSCRIBE"
    ANALYZE = "ANALYZE"
    RENDER = "RENDER"
    UPLOAD = "UPLOAD"

class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"

def uuid4():
    import uuid as _u
    return str(_u.uuid4())

class AppUser(Base):
    __tablename__ = "app_user"
    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    email = Column(Text, unique=True, nullable=True)
    api_key = Column(Text, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Video(Base):
    __tablename__ = "video"
    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    youtube_url = Column(Text, nullable=False)
    yt_video_id = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    duration_sec = Column(Integer, nullable=True)
    language = Column(Text, nullable=True)
    status = Column(Text, default="new")
    source_path = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    transcripts = relationship("Transcript", back_populates="video", cascade="all, delete-orphan")
    segments = relationship("Segment", back_populates="video", cascade="all, delete-orphan")
    clips = relationship("Clip", back_populates="video", cascade="all, delete-orphan")

class Transcript(Base):
    __tablename__ = "transcript"
    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    video_id = Column(UUID(as_uuid=False), ForeignKey("video.id"))
    language = Column(Text, nullable=True)
    text = Column(Text, nullable=True)
    words = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    video = relationship("Video", back_populates="transcripts")

class Segment(Base):
    __tablename__ = "segment"
    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    video_id = Column(UUID(as_uuid=False), ForeignKey("video.id"))
    t_start = Column(Float, nullable=False)
    t_end = Column(Float, nullable=False)
    features = Column(JSON, nullable=True)
    embedding = Column(JSON, nullable=True)
    score = Column(Float, nullable=True)
    reason = Column(JSON, nullable=True)
    status = Column(Text, default="candidate")
    video = relationship("Video", back_populates="segments")

class Clip(Base):
    __tablename__ = "clip"
    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    video_id = Column(UUID(as_uuid=False), ForeignKey("video.id"))
    segment_id = Column(UUID(as_uuid=False), ForeignKey("segment.id"), nullable=True)
    aspect_ratio = Column(Text, default="9:16")
    caption_style = Column(JSON, nullable=True)
    output_path = Column(Text, nullable=True)
    storage_url = Column(Text, nullable=True)
    status = Column(Text, default="queued")
    metrics = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    video = relationship("Video", back_populates="clips")

class Job(Base):
    __tablename__ = "job"
    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    video_id = Column(UUID(as_uuid=False), ForeignKey("video.id"))
    jtype = Column(Enum(JobType), nullable=False)
    status = Column(Enum(JobStatus), default=JobStatus.QUEUED)
    payload = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

class Signal(Base):
    __tablename__ = "signal"
    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    video_id = Column(UUID(as_uuid=False), ForeignKey("video.id"))
    source = Column(Text, nullable=True)
    ts = Column(Float, nullable=True)
    name = Column(Text, nullable=True)
    value = Column(Float, nullable=True)


class ChannelSub(Base):
    __tablename__ = "channel_sub"
    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    channel_id = Column(Text, nullable=False, unique=True)
    title = Column(Text, nullable=True)
    last_published_at = Column(DateTime, nullable=True)
    enabled = Column(Integer, default=1)  # 1=true, 0=false
    auto_render_top_k = Column(Integer, default=3)
    daily_post_time = Column(Text, nullable=True)  # "HH:MM" in UTC
    keywords = Column(JSON, nullable=True)  # default caption keywords


class AutoPost(Base):
    __tablename__ = "autopost"
    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    platform = Column(Text, nullable=False)  # 'webhook' | 'x'
    endpoint = Column(Text, nullable=True)   # webhook URL or handle (for 'x', ignored)
    template = Column(Text, nullable=True)   # e.g., "{title} — {views_24h} views in 24h {url}"
    daily_time = Column(Text, nullable=True) # "HH:MM" UTC
    enabled = Column(Integer, default=1)


class JobLog(Base):
    __tablename__ = "job_log"
    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    type = Column(Text, nullable=False)
    payload = Column(JSON, nullable=True)
    status = Column(Text, nullable=False, default="queued")  # queued|started|success|error
    error = Column(Text, nullable=True)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AlertChannel(Base):
    __tablename__ = "alert_channel"
    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    kind = Column(Text, nullable=False)  # 'slack' | 'webhook'
    endpoint = Column(Text, nullable=False)  # Slack webhook URL or generic webhook URL
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)


class AlertSettings(Base):
    __tablename__ = "alert_settings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    queue_threshold = Column(Integer, default=100)  # alert if Redis 'jobs' len >= threshold
    debounce_min = Column(Integer, default=10)      # minimum minutes between identical alerts
    health_enabled = Column(Integer, default=1)     # send alerts on health status changes
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MagicLink(Base):
    __tablename__ = "magic_link"
    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    token = Column(Text, nullable=False, unique=True)
    purpose = Column(Text, nullable=False)  # "approvals"
    email = Column(Text, nullable=True)
    meta = Column(JSON, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
