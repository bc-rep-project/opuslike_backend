import os, requests

BASE = "https://open.tiktokapis.com/v2"

def _auth_header():
    tok = os.getenv("TIKTOK_ACCESS_TOKEN")
    if not tok:
        raise RuntimeError("Set TIKTOK_ACCESS_TOKEN in env")
    return {"Authorization": f"Bearer {tok}"}

def upload_tiktok(file_path: str, title: str = "") -> str:
    # 1) initialize upload
    r = requests.post(f"{BASE}/video/upload/initialize/",
                      headers={**_auth_header(), "Content-Type": "application/json"},
                      json={"source_info": {"source": "FILE"}}, timeout=30)
    r.raise_for_status()
    data = r.json()
    upload_url = data.get("data",{}).get("upload_url")
    upload_id = data.get("data",{}).get("upload_id")
    if not upload_url or not upload_id:
        raise RuntimeError(f"Init failed: {r.text}")
    # 2) PUT the file to upload_url
    with open(file_path, "rb") as f:
        r2 = requests.put(upload_url, data=f, headers={"Content-Type":"video/mp4"}, timeout=120)
    if r2.status_code >= 300:
        raise RuntimeError(f"Upload failed: {r2.status_code} {r2.text}")
    # 3) publish
    body = {"upload_id": upload_id, "post_info": {"title": title[:150]}}
    r3 = requests.post(f"{BASE}/video/publish/",
                       headers={**_auth_header(), "Content-Type":"application/json"},
                       json=body, timeout=30)
    r3.raise_for_status()
    d3 = r3.json()
    vid = d3.get("data",{}).get("video_id")
    if not vid:
        raise RuntimeError(f"Publish failed: {r3.text}")
    return vid
