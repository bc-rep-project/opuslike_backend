import os, time, json, base64
from urllib.parse import urlparse
from typing import Optional

# S3 signing
def s3_client():
    import boto3
    return boto3.client(
        "s3",
        region_name=os.getenv("AWS_DEFAULT_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

# GCS signing
def gcs_client_and_signer():
    from google.cloud import storage as gcs
    # Support either default credentials or inline JSON
    creds_json = os.getenv("GCS_SERVICE_ACCOUNT_JSON")
    if creds_json:
        from google.oauth2 import service_account
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info)
        client = gcs.Client(credentials=creds, project=info.get("project_id"))
    else:
        client = gcs.Client()
    return client

def sign_url(object_path: str, expires_seconds: int = 3600) -> Optional[str]:
    """Return a signed, time-limited URL from an object_path like s3://bucket/key or gs://bucket/key.

    For local files, return None.
"""
    if object_path.startswith("s3://"):
        u = urlparse(object_path)
        bucket = u.netloc
        key = u.path.lstrip("/")
        client = s3_client()
        return client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
    if object_path.startswith("gs://"):
        u = urlparse(object_path)
        bucket = u.netloc
        key = u.path.lstrip("/")
        client = gcs_client_and_signer()
        b = client.bucket(bucket)
        blob = b.blob(key)
        return blob.generate_signed_url(expiration=expires_seconds, method="GET")
    return None
