import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

def get_creds():
    client_id = os.getenv("YT_CLIENT_ID")
    client_secret = os.getenv("YT_CLIENT_SECRET")
    refresh_token = os.getenv("YT_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token):
        raise RuntimeError("YouTube credentials not configured (YT_CLIENT_ID/SECRET/REFRESH_TOKEN)")
    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    # Ensure access token is refreshed
    creds.refresh(Request())
    return creds

def upload_youtube(file_path: str, meta: dict) -> str:
    creds = get_creds()
    yt = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": meta.get("title") or "Clip",
            "description": meta.get("description") or "",
            "tags": meta.get("tags") or []
        },
        "status": {
            "privacyStatus": meta.get("privacyStatus", "unlisted")
        }
    }
    media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        # Optionally, you can print progress: if status: print(int(status.progress()*100))
    if "id" not in response:
        raise RuntimeError("YouTube upload failed: " + str(response))
    return response["id"]
