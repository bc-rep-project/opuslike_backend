import os, hmac, hashlib, time, urllib.parse
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from sqlalchemy.orm import Session
from ..deps import get_db
from ..models import Clip, Video
from ..settings import settings
from .analytics import leaderboard as _leaderboard
from .admin import retry_job as _retry_job
from .health import health as _health

router = APIRouter()

def verify_slack(req: Request, body: bytes):
    ts = req.headers.get("X-Slack-Request-Timestamp")
    sig = req.headers.get("X-Slack-Signature")
    if not ts or not sig:
        return False
    if abs(time.time() - int(ts)) > 60 * 5:
        return False
    secret = os.getenv("SLACK_SIGNING_SECRET","").encode()
    base = b"v0:" + ts.encode() + b":" + body
    digest = "v0=" + hmac.new(secret, base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, sig)

@router.post("/slack/commands")
async def slack_commands(request: Request, db: Session = get_db()):
    raw = await request.body()
    if not verify_slack(request, raw):
        raise HTTPException(401, "bad signature")
    form = urllib.parse.parse_qs(raw.decode())
    cmd = (form.get("command",[None])[0] or "").strip()
    text = (form.get("text",[""'])[0] or "").strip()
    user = (form.get("user_name",["user"][0]))
    # Supported: /opus status | /opus top | /opus retry <job_id>
    if cmd == "/opus":
        parts = text.split()
        if not parts:
            return PlainTextResponse("Try: /opus status | /opus top | /opus retry <job_id>")
        sub = parts[0].lower()
        if sub == "status":
            # reuse health
            data = _health(db)
            q = data.get("checks",{}).get("redis",{}).get("queue_len",0)
            v = data.get("checks",{}).get("db",{}).get("ok",False)
            s = data.get("status")
            return PlainTextResponse(f"Status: {s} • DB: {'ok' if v else 'down'} • Queue: {q}")
        if sub == "pending":
            # Show up to 3 pending clips with Approve buttons
            from .approvals import pending as _pending
            pd = _pending(db, limit=3)
            blocks = []
            for it in pd.get('items', []):
                # use first suggestion as default title
                default_title = (it.get('suggestions') or [it.get('video_title') or 'Clip'])[0][:70]
                blocks.append({"type":"section","text":{"type":"mrkdwn","text":f"*{default_title}*\n`{it['clip_id'][:8]}` +{it.get('views_24h',0)} views/24h"}})
                if it.get('thumbnail_url'):
                    blocks.append({"type":"image","image_url": (request.url_for('slack_commands').replace('/slack/commands','') + it['thumbnail_url']), "alt_text":"thumbnail"})
                blocks.append({"type":"actions","elements":[
                    {"type":"button","text":{"type":"plain_text","text":"Approve (Unlisted)"},"action_id":"approve_unlisted","value":json.dumps({"clip_id": it['clip_id'], "title": default_title, "privacy":"unlisted"})},
                    {"type":"button","text":{"type":"plain_text","text":"Approve (Public)"},"style":"primary","action_id":"approve_public","value":json.dumps({"clip_id": it['clip_id'], "title": default_title, "privacy":"public"})}
                ]})
            return JSONResponse({"response_type":"ephemeral","blocks": blocks or [{"type":"section","text":{"type":"mrkdwn","text":"No pending clips."}}]})
        if sub == "top":
            lb = _leaderboard(db, window_days=1, limit=3)
            lines = []
            for idx, it in enumerate(lb.get("items", []), start=1):
                lines.append(f"{idx}. +{it['views_24h']} views — {it['title']} {it.get('youtube_url') or ''}".strip())
            return PlainTextResponse("\n".join(lines) if lines else "No data yet")
        if sub == "retry" and len(parts)>=2:
            job_id = parts[1]
            try:
                _retry_job(job_id, db=db)  # body default
                return PlainTextResponse(f"Requeued {job_id}")
            except Exception as e:
                return PlainTextResponse(f"Retry failed: {e}")
        return PlainTextResponse("Unknown subcommand")
    return PlainTextResponse("Unhandled command")


@router.post("/slack/actions")
async def slack_actions(request: Request):
    raw = await request.body()
    if not verify_slack(request, raw):
        raise HTTPException(401, "bad signature")
    import urllib.parse, json as _json
    form = urllib.parse.parse_qs(raw.decode())
    payload = _json.loads(form.get("payload", ["{}"])[0])
    action = None
    if payload.get("actions"):
        action = payload["actions"][0]
    if not action:
        return PlainTextResponse("no action")
    aid = action.get("action_id") or action.get("value")
    val = action.get("value") or ""
    # Expect value JSON like {"clip_id":"...", "title":"...", "privacy":"unlisted"}
    try:
        data = _json.loads(val) if val and val.strip().startswith("{") else {}
    except Exception:
        data = {}
    # approve flow
    if aid and aid.startswith("approve_"):
        from sqlalchemy.orm import Session
        from ..deps import get_db as _get_db
        from ..models import Clip, Video
        from .approvals import approve, ApproveBody
        db = _get_db()
        clip_id = data.get("clip_id")
        title = data.get("title") or ""
        privacy = data.get("privacy") or "unlisted"
        if not clip_id:
            return PlainTextResponse("missing clip_id")
        body = ApproveBody(title=title, style_key=None, publish_youtube=True, privacyStatus=privacy)
        # Create a fake request with x-api-key bypass (internal call); approvals now accepts magic or api-key.
        class DummyReq: headers = {"x-api-key": "internal"}
        try:
            approve(clip_id, body, DummyReq(), db)  # type: ignore
            msg = f"Queued upload for clip {clip_id}"
        except Exception as e:
            msg = f"Approve failed: {e}"
        return JSONResponse({"response_action":"update","text": msg})
    return PlainTextResponse("ok")
