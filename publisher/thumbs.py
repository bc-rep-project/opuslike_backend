import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from .youtube import get_creds

def set_thumbnail(video_id: str, image_path: str):
    creds = get_creds()
    yt = build("youtube","v3",credentials=creds)
    media = MediaFileUpload(image_path, mimetype="image/jpeg")
    resp = yt.thumbnails().set(videoId=video_id, media_body=media).execute()
    return resp
