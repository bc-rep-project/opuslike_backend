import os, time, requests, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from redis import Redis
from sqlalchemy.orm import Session
from shared.db import SessionLocal
from api.models import ChannelSub, Video
from api.settings import settings

RSS = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"

def parse_rss(xml_text):
    root = ET.fromstring(xml_text)
    ns = {'yt': 'http://www.youtube.com/xml/schemas/2015', 'atom': 'http://www.w3.org/2005/Atom'}
    items = []
    for e in root.findall('atom:entry', ns):
        vid = e.find('yt:videoId', ns).text
        published = e.find('atom:published', ns).text
        title = e.find('atom:title', ns).text
        dt = datetime.fromisoformat(published.replace('Z', '+00:00'))
        items.append({'video_id': vid, 'title': title, 'published': dt})
    items.sort(key=lambda x: x['published'])
    return items

def loop():
    r = Redis.from_url(settings.REDIS_URL)
    while True:
        try:
            db: Session = SessionLocal()
            subs = db.query(ChannelSub).filter_by(enabled=1).all()
            now = datetime.now(timezone.utc)
            for s in subs:
                # 1) fetch RSS and enqueue new videos
                try:
                    xml = requests.get(RSS.format(cid=s.channel_id), timeout=15).text
                    items = parse_rss(xml)
                except Exception as e:
                    print("RSS error:", s.channel_id, e)
                    items = []
                last = s.last_published_at
                for it in items:
                    if (not last) or (it['published'] > last):
                        url = f"https://www.youtube.com/watch?v={it['video_id']}"
                        # create DB video if doesn't exist
                        exists = db.query(Video).filter_by(youtube_url=url).first()
                        if not exists:
                            v = Video(youtube_url=url, status="queued")
                            db.add(v); db.commit(); db.refresh(v)
                            # queue ingest
                            r.lpush("jobs", f'{{"type":"INGEST","video_id":"{v.id}","youtube_url":"{v.youtube_url}"}}')
                        s.last_published_at = it['published']
                        db.commit()
                # 2) daily auto-render window
                if s.daily_post_time:
                    hh, mm = map(int, s.daily_post_time.split(":"))
                    if now.hour == hh and now.minute == mm:
                        # pick the most recent analyzed video without clips
                        v = db.query(Video).filter_by(status="analyze_done").order_by(Video.created_at.desc()).first()
                        if v:
                            payload = {"type":"AUTO_RENDER","video_id": v.id, "top_k": s.auto_render_top_k, "opts":{"dynamic_reframe": True, "face_reframe": True, "caption_style":{"keywords": s.keywords or []}, "broll_on_pauses": True}}
                            r.lpush("jobs", __import__("json").dumps(payload))
            db.close()
        except Exception as e:
            print("Scheduler loop error:", e)
        time.sleep(60)

if __name__ == "__main__":
    print("Scheduler started")
    loop()


    # Daily analytics refresh at 03:00 UTC
    def maybe_enqueue_analytics(r):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        if now.hour == 3 and now.minute == 0:
            r.lpush("jobs", '{"type":"ANALYTICS_REFRESH"}')



def maybe_enqueue_ab_switch(r):
    from sqlalchemy.orm import Session
    from shared.db import SessionLocal
    from api.models import Clip
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if now.hour == 6 and now.minute == 0:
        db: Session = SessionLocal()
        rows = db.query(Clip).filter_by(ab_status="running").all()
        for c in rows:
            next_v = "B" if (c.ab_active or "A") == "A" else "A"
            r.lpush("jobs", '{"type":"THUMB_SET_YT","clip_id":"%s","variant":"%s"}' % (c.id, next_v))
        db.close()


def maybe_evaluate_ab(r):
    """At 07:00 UTC, evaluate running A/B tests after N days (AB_EVAL_DAYS, default 4) using daily view deltas."""
    from datetime import datetime, timezone, timedelta
    from shared.db import SessionLocal
    from sqlalchemy.orm import Session
    from api.models import Clip
    N = int(os.getenv("AB_EVAL_DAYS", "4"))
    now = datetime.now(timezone.utc)
    if not (now.hour == 7 and now.minute == 0):
        return
    db: Session = SessionLocal()
    rows = db.query(Clip).filter_by(ab_status="running").all()
    for c in rows:
        m = c.metrics or {}
        series = m.get("youtube_timeseries") or []
        # need at least N+1 points to compute N deltas
        if len(series) < N+1:
            continue
        # Build date->views mapping
        series_sorted = sorted(series, key=lambda x: x.get("date"))
        deltas = []
        for i in range(1, len(series_sorted)):
            try:
                d0 = int(series_sorted[i-1].get("views",0)); d1 = int(series_sorted[i].get("views",0))
                deltas.append((series_sorted[i]["date"], max(0, d1 - d0)))
            except Exception:
                continue
        # Determine active variant for each date using ab_history
        hist = c.ab_history or []
        # Build a date->variant map by stepping through history in order
        # Default to current ab_active for dates after last recorded event
        vmap = {}
        current = None
        # Use first event variant if exists, else A
        if hist:
            # sort by ts
            hist_sorted = sorted([h for h in hist if "ts" in h], key=lambda x: x["ts"])
            current = hist_sorted[0].get("variant","A")
            for h in hist_sorted:
                ts = h.get("ts","")[:10]
                if h.get("event","").startswith("switch") or h.get("event","").startswith("ab_start"):
                    current = h.get("variant", current or "A")
                vmap[ts] = current
        else:
            current = c.ab_active or "A"
        # Sum last N days by variant
        A=B=0
        for (d, dv) in deltas[-N:]:
            variant = vmap.get(d, current or "A")
            if variant == "A": A += dv
            else: B += dv
        # Decide winner if any non-zero and difference significant (>0)
        if (A + B) > 0:
            winner = "A" if A >= B else "B"
            # Stop test and set winner
            c.ab_status = "stopped"; c.ab_active = winner
            hist = c.ab_history or []
            hist.append({"ts": now.isoformat(), "event":"ab_stop_winner", "winner": winner, "A": A, "B": B})
            c.ab_history = hist
            db.commit()
            # enqueue YouTube thumb set
            r.lpush("jobs", '{"type":"THUMB_SET_YT","clip_id":"%s","variant":"%s"}' % (c.id, winner))
    db.close()


def maybe_run_autoposts(r):
    from shared.db import SessionLocal
    from sqlalchemy.orm import Session
    from api.models import AutoPost
    from datetime import datetime, timezone
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    hhmm = f"{now.hour:02d}:{now.minute:02d}"
    rows = db.query(AutoPost).filter_by(enabled=1).all()
    for ap in rows:
        if ap.daily_time == hhmm:
            r.lpush("jobs", '{"type":"AUTOPOST_FIRE","autopost_id":"%s"}' % ap.id)
    db.close()


def _health_snapshot():
    from sqlalchemy.orm import Session
    from shared.db import SessionLocal
    from redis import Redis
    from api.settings import settings
    import os
    ok_db = False
    qlen = 0
    try:
        db: Session = SessionLocal()
        db.execute("SELECT 1")
        ok_db = True
        db.close()
    except Exception:
        ok_db = False
    ok_redis = False
    try:
        r = Redis.from_url(settings.REDIS_URL)
        ok_redis = bool(r.ping())
        qlen = int(r.llen("jobs"))
    except Exception:
        ok_redis = False
    root = os.getenv("MEDIA_ROOT", "/data")
    ok_storage = os.path.isdir(root) and os.access(root, os.W_OK)
    status = "ok" if (ok_db and ok_redis and ok_storage) else "degraded"
    return {"status": status, "queue_len": qlen}

def maybe_monitor_alerts(r):
    from api.models import AlertChannel, AlertSettings
    from shared.db import SessionLocal
    from sqlalchemy.orm import Session
    from datetime import datetime, timezone, timedelta
    import json as _json
    import requests
    db: Session = SessionLocal()
    chans = db.query(AlertChannel).filter_by(enabled=1).all()
    settings = db.query(AlertSettings).first()
    if not settings:
        settings = AlertSettings(); db.add(settings); db.commit(); db.refresh(settings)
    snap = _health_snapshot()
    now = datetime.now(timezone.utc)
    key_status = "alert:last_status"
    key_queue_ts = "alert:last_queue_ts"
    # Use Redis for state
    from redis import Redis as _Redis
    from api.settings import settings as cfg
    rc = _Redis.from_url(cfg.REDIS_URL)
    last_status = rc.get(key_status)
    last_status = last_status.decode() if last_status else None
    if int(settings.health_enabled or 0) == 1 and last_status and last_status != snap["status"]:
        # status changed
        msg = f"Health status changed: {last_status} → {snap['status']} (queue={snap['queue_len']})"
        for ch in chans:
            try:
                if ch.kind == "slack":
                    requests.post(ch.endpoint, json={"text": msg}, timeout=10)
                else:
                    requests.post(ch.endpoint, json={"type":"health_change","message": msg, "snapshot": snap}, timeout=10)
            except Exception as e:
                print("alert send failed:", e)
    rc.set(key_status, snap["status"])

    # Queue spike alert with debounce
    thr = int(settings.queue_threshold or 100)
    if snap["queue_len"] >= thr:
        last_ts = rc.get(key_queue_ts)
        debounce_min = int(settings.debounce_min or 10)
        allow = True
        if last_ts:
            try:
                last = datetime.fromtimestamp(float(last_ts.decode()), tz=timezone.utc)
                allow = (now - last) >= timedelta(minutes=debounce_min)
            except Exception:
                allow = True
        if allow:
            msg = f"Jobs queue high: len={snap['queue_len']} (>= {thr})"
            for ch in chans:
                try:
                    if ch.kind == "slack":
                        requests.post(ch.endpoint, json={"text": msg}, timeout=10)
                    else:
                        requests.post(ch.endpoint, json={"type":"queue_spike","message": msg, "snapshot": snap}, timeout=10)
                except Exception as e:
                    print("alert send failed:", e)
            rc.set(key_queue_ts, str(now.timestamp()))
    db.close()
