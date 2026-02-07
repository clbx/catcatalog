"""Web UI service — serves frontend and proxies S3 crop images."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from ..storage import download_to_temp, get_bucket, get_s3_client

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Cat Catalog — Web UI")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/crop/{key:path}")
def get_crop(key: str):
    """Proxy a crop image from S3."""
    s3 = get_s3_client()
    try:
        resp = s3.get_object(Bucket=get_bucket(), Key=key)
        data = resp["Body"].read()
        content_type = resp.get("ContentType", "image/jpeg")
        return Response(content=data, media_type=content_type)
    except Exception:
        return Response(status_code=404, content=b"Not found")


@app.get("/api/video/{key:path}")
def get_video(key: str):
    """Proxy a video file from S3."""
    s3 = get_s3_client()
    try:
        resp = s3.get_object(Bucket=get_bucket(), Key=key)
        data = resp["Body"].read()
        content_type = resp.get("ContentType", "video/mp4")
        return Response(content=data, media_type=content_type)
    except Exception:
        return Response(status_code=404, content=b"Not found")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
