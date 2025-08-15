import os, subprocess
from faster_whisper import WhisperModel
from sentence_transformers import SentenceTransformer

WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "small")
DEVICE = os.getenv("DEVICE", "cpu")
WHISPER_MODEL = WhisperModel(WHISPER_MODEL_NAME, device=DEVICE)
EMB_MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def download_video(youtube_url: str, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "%(id)s.%(ext)s")
    cmd = ["yt-dlp","-f","mp4","-o", out, youtube_url]
    subprocess.check_call(cmd)
    for f in os.listdir(out_dir):
        if f.endswith(".mp4"):
            return os.path.join(out_dir, f)
    raise RuntimeError("mp4 not found")

def transcribe(path: str):
    segments, info = WHISPER_MODEL.transcribe(path, word_timestamps=True)
    words, full = [], []
    for seg in segments:
        full.append(seg.text.strip())
        if seg.words:
            for w in seg.words:
                words.append({"w": w.word, "start": float(w.start), "end": float(w.end)})
    return {"text": " ".join(full), "words": words, "lang": info.language}

def sliding_windows(words, target_len=30.0, stride=10.0):
    i, n = 0, len(words)
    while i < n:
        t0 = words[i]["start"]
        j = i
        while j < n and words[j]["end"] - t0 < target_len:
            j += 1
        t1 = words[j-1]["end"] if j > i else t0 + target_len
        yield t0, t1, words[i:j]
        while i < n and words[i]["start"] < t0 + stride:
            i += 1

def text_features(tokens):
    txt = "".join([w["w"] for w in tokens]).strip()
    exclam = txt.count("!") + txt.lower().count("wow")
    avg_word = (sum(len(w["w"]) for w in tokens)/len(tokens)) if tokens else 5.0
    quoteability = 1.0 / max(1.0, avg_word)
    emb = EMB_MODEL.encode([txt], normalize_embeddings=True)[0].tolist()
    return {"exclam": int(exclam), "quoteability": float(quoteability)}, emb

def overlap(a, b, iou_thr=0.3):
    inter = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    union = (a["end"]-a["start"]) + (b["end"]-b["start"]) - inter
    return (inter/union) > iou_thr

def rank_segments(words):
    rows = []
    for t0, t1, toks in sliding_windows(words):
        f, emb = text_features(toks)
        score = 0.6*f["quoteability"] + (0.4 if f["exclam"]>0 else 0.0)
        rows.append({"start": t0, "end": t1, "score": float(score), "features": f, "embedding": emb})
    rows.sort(key=lambda r: r["score"], reverse=True)
    keep, used = [], []
    for r in rows:
        if all(not overlap(r, u) for u in used):
            keep.append(r); used.append(r)
        if len(keep) >= 12: break
    return keep


def to_srt(words, out_path, max_gap=0.6):
    def ts(x):
        h=int(x//3600); m=int((x%3600)//60); s=x%60
        return f"{h:02}:{m:02}:{s:06.3f}".replace('.',',')
    chunks, cur = [], []
    for i,w in enumerate(words):
        cur.append(w)
        if i+1==len(words) or (words[i+1]["start"]-w["end"])>max_gap:
            chunks.append((cur[0]["start"], cur[-1]["end"], "".join([t["w"] for t in cur]).strip()))
            cur=[]
    with open(out_path,"w",encoding="utf-8") as f:
        for i,(s,e,txt) in enumerate(chunks,1):
            f.write(f"{i}\n{ts(s)} --> {ts(e)}\n{txt}\n\n")

def to_ass(words, out_path, keywords=None, max_gap=0.6, font="Inter", font_size=48, primary_color="&H00FFFFFF", emphasis_color="&H0000FF00"):
    """Build a minimal ASS file. keywords (list[str]) will be bold+colored when matched case-insensitively.
    Colors use ASS BGR hex (&H00BBGGRR)."""
    import re
    def ts(x):
        h=int(x//3600); m=int((x%3600)//60); s=x%60
        return f"{h:01d}:{m:02d}:{s:05.2f}"
    # group into chunks
    chunks, cur = [], []
    for i,w in enumerate(words):
        cur.append(w)
        if i+1==len(words) or (words[i+1]["start"]-w["end"])>max_gap:
            txt = "".join([t["w"] for t in cur]).strip()
            chunks.append((cur[0]["start"], cur[-1]["end"], txt))
            cur=[]
    kw = [k.strip() for k in (keywords or []) if k.strip()]
    def emph(txt):
        if not kw: return txt
        out = txt
        for k in kw:
            try:
                out = re.sub(rf"(?i)\b({re.escape(k)})\b", r"{\b1\c%s}\1{\b0\c%s}" % (emphasis_color, primary_color), out)
            except re.error:
                pass
        return out
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{primary_color},&H000000FF,&H00101010,&H64000000,0,0,0,0,100,100,0,0,1,2,0,2,40,40,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header)
        for (s,e,txt) in chunks:
            line = emph(txt).replace("\n"," ")
            f.write(f"Dialogue: 0,{ts(s)},{ts(e)},Default,,0,0,0,,{line}\n")

def compute_face_crop(input_path: str, start: float, end: float, target_h: int = 1920, crop_w: int = 1080, sample_fps: float = 2.0):
    """Sample frames in [start,end], detect faces with Haar, and return (scaled_width, x_offset) for 9:16 crop."""
    import cv2
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    orig_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920
    orig_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080
    scale = target_h / float(orig_h)
    scaled_w = orig_w * scale
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    xs = []
    total_frames = int(max(1, (end - start) * sample_fps))
    for i in range(total_frames):
        t = start + i / sample_fps
        frame_idx = int(t * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60,60))
        if len(faces) > 0:
            x,y,w,h = max(faces, key=lambda f: f[2]*f[3])
            center_x = (x + w/2.0) * scale
            xs.append(center_x)
    cap.release()
    if not xs:
        return int(scaled_w), int(max(0, (scaled_w - crop_w)/2))
    xs.sort()
    med = xs[len(xs)//2]
    x0 = int(round(med - crop_w/2))
    x0 = max(0, min(int(scaled_w - crop_w), x0))
    return int(round(scaled_w)), x0

def render_clip(input_path, start, end, out_path, aspect="9:16", srt_path=None, crop_hint=None):
    vf = 'scale=-2:1920,crop=1080:1920'
    if aspect == "1:1":
        vf = 'scale=1080:-2,crop=1080:1080'
    if aspect == "16:9":
        vf = 'scale=1920:-2'
    if crop_hint and aspect == "9:16":
        scaled_w, x0 = crop_hint
        vf = f'scale={int(round(scaled_w))}:1920,crop=1080:1920:{x0}:0'
    if srt_path:
        vf = vf + f",subtitles='{srt_path}'"
    cmd = ["ffmpeg","-y","-ss",f"{start}","-to",f"{end}","-i", input_path,"-vf", vf,"-r","30","-c:v","libx264","-preset","veryfast","-crf","18","-c:a","aac","-b:a","160k", out_path]
    import subprocess
    subprocess.check_call(cmd)
    return out_path


def compute_face_track(input_path: str, start: float, end: float, target_h: int = 1920, crop_w: int = 1080, sample_fps: float = 10.0):
    """Lightweight face tracker: detect faces periodically, track between detections (CSRT/KCF/MOSSE).
    Returns (scaled_w, [(t_relative_sec, x0_int), ...]) where x0 is the left crop offset in the scaled domain."""
    import cv2
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        return None, []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    ow = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920
    oh = cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080
    scale = target_h / float(oh)
    scaled_w = int(round(ow * scale))

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    tracker = None
    def create_tracker():
        nonlocal tracker
        for name in ["TrackerCSRT", "TrackerKCF", "TrackerMOSSE"]:
            ctor = getattr(cv2, f"{name}_create", None)
            if ctor:
                tracker = ctor()
                return True
        tracker = None
        return False

    def detect_face(frame_gray):
        faces = face_cascade.detectMultiScale(frame_gray, scaleFactor=1.1, minNeighbors=5, minSize=(60,60))
        if len(faces) == 0:
            return None
        x,y,w,h = max(faces, key=lambda f: f[2]*f[3])
        return (int(x), int(y), int(w), int(h))

    interval = 1.0 / sample_fps
    t = start
    track = []
    bbox = None
    reinit_every = 1.0  # seconds
    last_detect_t = -1e9

    while t <= end + 1e-6:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            t += interval
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        need_redetect = (t - last_detect_t) > reinit_every or tracker is None
        if need_redetect:
            b = detect_face(gray)
            if b is not None:
                bbox = b
                create_tracker()
                if tracker:
                    tracker.init(frame, bbox)
                last_detect_t = t
        else:
            if tracker and bbox is not None:
                ok, bbox_new = tracker.update(frame)
                if ok:
                    bbox = tuple(int(v) for v in bbox_new)
                else:
                    last_detect_t = -1e9

        if bbox is not None:
            x,y,w,h = bbox
            cx_scaled = (x + w/2.0) * scale
            x0 = int(round(max(0, min(scaled_w - crop_w, cx_scaled - crop_w/2.0))))
            trel = t - start
            track.append((trel, x0))

        t += interval

    cap.release()

    if track:
        import numpy as np
        times = np.array([p[0] for p in track], dtype=float)
        xs = np.array([p[1] for p in track], dtype=float)
        win = 9
        pad = win // 2
        xs_pad = np.pad(xs, (pad,pad), mode="edge")
        kernel = np.ones(win) / win
        xs_smooth = np.convolve(xs_pad, kernel, mode="valid")
        track = list(zip(times.tolist(), [int(round(v)) for v in xs_smooth.tolist()]))

    return scaled_w, track

def find_pauses(words, start, end, thr=0.8, max_items=3):
    # Return up to max_items (t_start, t_end) within [start,end] where no words occur for >= thr seconds
    spans = []
    ws = [w for w in words if w["start"]>=start and w["end"]<=end]
    if not ws:
        return spans
    last = start
    for w in ws:
        gap = w["start"] - last
        if gap >= thr:
            spans.append((last, min(w["start"], end)))
        last = w["end"]
    if end - last >= thr:
        spans.append((last, end))
    # clip to max_items and minimal 1.2s duration each
    out = []
    for s,e in spans:
        dur = e - s
        if dur >= thr:
            out.append((s, min(e, s+1.8)))
        if len(out) >= max_items:
            break
    return out

def choose_broll(broll_dir, n=2):
    try:
        files = [os.path.join(broll_dir, f) for f in os.listdir(broll_dir) if f.lower().endswith(('.mp4','.mov','.mkv','.webm'))]
    except Exception:
        files = []
    random.shuffle(files)
    return files[:n]

def generate_thumbnail(input_path, start, end, out_path, aspect="9:16", crop_hint=None, title=None):
    """Extract a mid-frame, apply same crop, and optionally overlay a title with PIL; saves JPEG."""
    import subprocess, tempfile, os
    from PIL import Image, ImageDraw, ImageFont

    tmid = (start + end) / 2.0
    # Build scale/crop filter similar to render_clip
    vf = 'scale=-2:1920,crop=1080:1920'
    if aspect == "1:1":
        vf = 'scale=1080:-2,crop=1080:1080'
    if aspect == "16:9":
        vf = 'scale=1920:-2'
    if crop_hint and aspect == "9:16":
        scaled_w, x0 = crop_hint
        vf = f'scale={int(round(scaled_w))}:1920,crop=1080:1920:{x0}:0'

    tmp_png = out_path + ".png"
    cmd = ["ffmpeg","-y","-ss", f"{tmid}","-i", input_path,"-vframes","1","-vf", vf, tmp_png]
    subprocess.check_call(cmd)

    # Open and draw overlay
    im = Image.open(tmp_png).convert("RGB")
    W,H = im.size
    draw = ImageDraw.Draw(im)
    # gradient bar at top
    bar_h = int(H*0.22)
    for i in range(bar_h):
        a = int(200 * (1.0 - i/bar_h))  # fade out
        draw.rectangle([0, i, W, i], fill=(0,0,0,a))
    txt = title or "Clip"
    try:
        # Try a common font path; fallback to default
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size=int(H*0.06))
    except Exception:
        font = ImageFont.load_default()
    # Wrap text
    max_w = int(W*0.92)
    words = txt.split()
    lines=[]; cur=""
    for w in words:
        test = (cur+" "+w).strip()
        bw, bh = draw.textbbox((0,0), test, font=font)[2:]
        if bw <= max_w:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    y = int(H*0.04)
    for line in lines[:3]:
        # stroke
        draw.text((int(W*0.04)+1, y+1), line, font=font, fill=(0,0,0))
        draw.text((int(W*0.04)-1, y-1), line, font=font, fill=(0,0,0))
        draw.text((int(W*0.04), y), line, font=font, fill=(255,255,255))
        y += int(bh*1.1 if 'bh' in locals() else H*0.07)
    im.save(out_path, quality=92)
    try: os.remove(tmp_png)
    except Exception: pass
    return out_path
