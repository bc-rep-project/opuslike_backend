from typing import List, Dict
from googleapiclient.discovery import build
from .youtube import get_creds

def get_video_stats(video_ids: List[str]) -> Dict[str, dict]:
    creds = get_creds()
    yt = build("youtube", "v3", credentials=creds)
    out = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        resp = yt.videos().list(part="statistics", id=",".join(chunk)).execute()
        for item in resp.get("items", []):
            vid = item["id"]
            st = item.get("statistics", {})
            out[vid] = {
                "views": int(st.get("viewCount", 0)),
                "likes": int(st.get("likeCount", 0)),
                "comments": int(st.get("commentCount", 0)),
            }
    return out


def get_video_impressions(video_ids, start_date: str, end_date: str):
    """Return dict {videoId: {'impressions': int, 'views': int}} for the date range (typically one day).
    Requires refresh token with scope yt-analytics.readonly."""
    if not video_ids:
        return {}
    creds = get_creds()
    ya = build("youtubeAnalytics", "v2", credentials=creds)
    out = {}
    # YouTube Analytics supports comma-separated list in filters video==
    # But responses come aggregated per video row when dimensions=video.
    vids_join = ",".join(video_ids[:200])  # cap
    resp = ya.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        metrics="impressions,views",
        dimensions="video",
        filters=f"video=={vids_join}",
        maxResults=200
    ).execute()
    cols = [c["name"] for c in resp.get("columnHeaders", [])]
    v_idx = cols.index("video")
    imp_idx = cols.index("impressions")
    views_idx = cols.index("views")
    for row in resp.get("rows", []):
        vid = row[v_idx]
        out[vid] = {"impressions": int(row[imp_idx]), "views": int(row[views_idx])}
    return out
