"""Shared S3 storage client for all services."""

import os
import tempfile
from pathlib import Path

import boto3
from botocore.config import Config


def get_s3_client():
    """Create an S3 client from environment variables.

    Env vars:
        S3_ENDPOINT_URL  — custom endpoint (for MinIO, LocalStack, etc.)
        S3_REGION        — AWS region (default: us-east-1)
        AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY — credentials
    """
    kwargs = {
        "region_name": os.environ.get("S3_REGION", "us-east-1"),
    }
    endpoint = os.environ.get("S3_ENDPOINT_URL")
    if endpoint:
        kwargs["endpoint_url"] = endpoint
        kwargs["config"] = Config(s3={"addressing_style": "path"})

    return boto3.client("s3", **kwargs)


def get_bucket():
    """Get the configured bucket name."""
    return os.environ.get("S3_BUCKET", "catcatalog")


def download_to_temp(key):
    """Download an S3 object to a temp file. Returns the temp file path.

    Caller is responsible for cleanup.
    """
    s3 = get_s3_client()
    suffix = Path(key).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    s3.download_fileobj(get_bucket(), key, tmp)
    tmp.close()
    return Path(tmp.name)


def upload_file(local_path, key, content_type=None):
    """Upload a local file to S3."""
    s3 = get_s3_client()
    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type
    s3.upload_file(str(local_path), get_bucket(), key, ExtraArgs=extra_args)


def upload_bytes(data, key, content_type=None):
    """Upload raw bytes to S3."""
    import io

    s3 = get_s3_client()
    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type
    s3.upload_fileobj(io.BytesIO(data), get_bucket(), key, ExtraArgs=extra_args)


def list_objects(prefix):
    """List object keys under a prefix."""
    s3 = get_s3_client()
    bucket = get_bucket()
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def move_object(src_key, dst_key):
    """Move an object from one key to another within the same bucket."""
    s3 = get_s3_client()
    bucket = get_bucket()
    s3.copy_object(
        Bucket=bucket, CopySource={"Bucket": bucket, "Key": src_key}, Key=dst_key
    )
    s3.delete_object(Bucket=bucket, Key=src_key)


def object_exists(key):
    """Check if an object exists in S3."""
    s3 = get_s3_client()
    try:
        s3.head_object(Bucket=get_bucket(), Key=key)
        return True
    except s3.exceptions.ClientError:
        return False


def acquire_lock(key, worker_id, ttl_seconds=300):
    """Try to create a .lock file for a key. Returns True if lock acquired.

    The lock file contains the worker ID and expiry timestamp.
    If a stale lock exists (past TTL), it gets overwritten.
    """
    import json
    import time

    lock_key = key + ".lock"
    s3 = get_s3_client()
    bucket = get_bucket()

    # Check for existing lock
    try:
        resp = s3.get_object(Bucket=bucket, Key=lock_key)
        lock_data = json.loads(resp["Body"].read())
        # If lock is still valid, another worker has it
        if lock_data.get("expires", 0) > time.time():
            return False
        # Stale lock — fall through and overwrite
    except s3.exceptions.ClientError:
        pass  # No lock exists

    # Create lock
    lock_data = {
        "worker_id": worker_id,
        "locked_at": time.time(),
        "expires": time.time() + ttl_seconds,
    }
    s3.put_object(
        Bucket=bucket,
        Key=lock_key,
        Body=json.dumps(lock_data).encode(),
        ContentType="application/json",
    )
    return True


def release_lock(key):
    """Delete the .lock file for a key."""
    s3 = get_s3_client()
    s3.delete_object(Bucket=get_bucket(), Key=key + ".lock")
