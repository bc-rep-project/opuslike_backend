import os, json, tempfile
from redis import Redis
from sqlalchemy.orm import Session
from shared.db import SessionLocal
from api.models import Video, Transcript, Segment, Clip
from .pipeline import download_video, transcribe, rank_segments, to_srt, render_clip

r = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))

def with_db():
    db = SessionLocal()
    try:
            pass
        except Exception as e:
            # mark error to job log early
            try:
                if 'log_id' in locals() and log_id:
                    for db in with_db():
                        jl = db.query(JobLog).filter_by(id=log_id).first()
                        if jl:
                            jl.status = 'error'; jl.error = str(e); db.commit()
            except Exception:
                pass
        try:
        yield db
    finally:
        db.close()

def handle(job: dict):
    jtype = job.get("type")
            log_id = None
            try:
            pass
        except Exception as e:
            # mark error to job log early
            try:
                if 'log_id' in locals() and log_id:
                    for db in with_db():
                        jl = db.query(JobLog).filter_by(id=log_id).first()
                        if jl:
                            jl.status = 'error'; jl.error = str(e); db.commit()
            except Exception:
                pass
        try:
                for db in with_db():
                    jl = JobLog(type=jtype, payload=job, status="started", attempts=1)
                    db.add(jl); db.commit(); db.refresh(jl)
                    log_id = jl.id
            except Exception as _e:
                log_id = None

    if jtype == "INGEST":
        video_id = job["video_id"]; youtube_url = job["youtube_url"]
        tdir = tempfile.mkdtemp()
        path = download_video(youtube_url, tdir)
        for db in with_db():
            v = db.query(Video).filter_by(id=video_id).first()
            if v: v.source_path = path; v.status = "downloaded"; db.commit()
        r.lpush("jobs", json.dumps({"type":"TRANSCRIBE","video_id":video_id,"path":path}))
    elif jtype == "TRANSCRIBE":
        video_id = job["video_id"]; path = job["path"]
        res = transcribe(path)
        for db in with_db():
            t = Transcript(video_id=video_id, language=res.get("lang"), text=res.get("text"), words=res.get("words"))
            v = db.query(Video).filter_by(id=video_id).first()
            if v: v.status = "transcribed"
            db.add(t); db.commit()
        r.lpush("jobs", json.dumps({"type":"ANALYZE","video_id":video_id}))
    elif jtype == "ANALYZE":
        video_id = job["video_id"]
        for db in with_db():
            t = (db.query(Transcript).filter_by(video_id=video_id).order_by(Transcript.created_at.desc()).first())
            if not t or not t.words: return
            moments = rank_segments(t.words)
            for m in moments:
                seg = Segment(video_id=video_id, t_start=m["start"], t_end=m["end"], features=m["features"], embedding=m["embedding"], score=m["score"], reason={"quoteability": m["features"]["quoteability"], "exclam": m["features"]["exclam"]})
                db.add(seg)
            v = db.query(Video).filter_by(id=video_id).first()
            if v: v.status = "analyze_done"
            db.commit()
    elif jtype == "RENDER":
        video_id = job["video_id"]; clip_id = job["clip_id"]; segment_id = job["segment_id"]; aspect = job.get("aspect_ratio","9:16")
        for db in with_db():
            v = db.query(Video).filter_by(id=video_id).first()
            s = db.query(Segment).filter_by(id=segment_id).first()
            if not (v and v.source_path and s): return
            base_dir = os.getenv("MEDIA_ROOT", "/data")
            os.makedirs(os.path.join(base_dir, "clips"), exist_ok=True)
            # Subtitles
            srt_path = None
            t = (db.query(Transcript).filter_by(video_id=video_id).order_by(Transcript.created_at.desc()).first())
            if t and t.words:
                srt_path = os.path.join(base_dir, "clips", f"{clip_id}.srt")
                to_srt(t.words, srt_path)
            out = os.path.join(base_dir, "clips", f"{clip_id}.mp4")
            render_clip(v.source_path, s.t_start, s.t_end, out, aspect, srt_path)
            c = db.query(Clip).filter_by(id=clip_id).first()
            c.output_path = out
            c.storage_url = f"/static/clips/{clip_id}.mp4"
            c.status = "rendered"
            db.commit()
    else:
        print("Unknown job:", job)

if __name__ == "__main__":
    print("Worker started. Waiting for jobs...")
    while True:
        _, raw = r.brpop("jobs")
        try:
            pass
        except Exception as e:
            # mark error to job log early
            try:
                if 'log_id' in locals() and log_id:
                    for db in with_db():
                        jl = db.query(JobLog).filter_by(id=log_id).first()
                        if jl:
                            jl.status = 'error'; jl.error = str(e); db.commit()
            except Exception:
                pass
        try:
            job = json.loads(raw)
        except Exception:
            print("Invalid job:", raw); continue
        try:
            pass
        except Exception as e:
            # mark error to job log early
            try:
                if 'log_id' in locals() and log_id:
                    for db in with_db():
                        jl = db.query(JobLog).filter_by(id=log_id).first()
                        if jl:
                            jl.status = 'error'; jl.error = str(e); db.commit()
            except Exception:
                pass
        try:
            handle(job)
        except Exception as e:
            print("Job failed:", e)
