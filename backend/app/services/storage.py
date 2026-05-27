"""MinIO / S3 storage helper — upload + signed/public URL generation.

The bucket is created lazily on first use. URLs returned are PUBLIC (no
signing) since the dev MinIO is configured for direct read access. For prod
behind a CDN, swap `_public_url` to return a signed URL with an expiration.
"""
from __future__ import annotations

import logging
import mimetypes
import uuid
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        config=Config(signature_version="s3v4"),
    )


def _ensure_bucket(s3, bucket: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchBucket", "NoSuchKey"):
            s3.create_bucket(Bucket=bucket)
            # Make it public-read for dev convenience. In prod use signed URLs.
            try:
                s3.put_bucket_policy(
                    Bucket=bucket,
                    Policy='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":"*","Action":"s3:GetObject","Resource":"arn:aws:s3:::'
                    + bucket
                    + '/*"}]}',
                )
            except ClientError:
                logger.warning("Could not set public-read policy on %s", bucket, exc_info=True)
        else:
            raise


def _public_url(key: str) -> str:
    """Resolve a stored key to a URL the browser can fetch directly."""
    base = settings.S3_PUBLIC_URL.rstrip("/")
    return f"{base}/{settings.S3_BUCKET}/{key}"


def upload_bytes(
    *,
    key_prefix: str,
    filename: str,
    data: bytes,
    content_type: Optional[str] = None,
) -> tuple[str, str, int]:
    """Upload `data` under `<key_prefix>/<uuid>-<filename>` and return
    `(url, stored_key, size)`."""
    s3 = _client()
    _ensure_bucket(s3, settings.S3_BUCKET)

    safe_name = filename.replace("/", "_").replace("\\", "_")
    key = f"{key_prefix.strip('/')}/{uuid.uuid4().hex}-{safe_name}"

    if not content_type:
        guessed, _ = mimetypes.guess_type(safe_name)
        content_type = guessed or "application/octet-stream"

    s3.put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
        ACL="public-read",
    )
    return _public_url(key), key, len(data)
