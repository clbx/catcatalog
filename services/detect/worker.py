"""Detection worker — polls S3 ingest prefix, processes files, posts results to catalog."""

import os
import platform
import threading
import time
import uuid
from pathlib import Path

import cv2
import requests

from ..storage import (
    acquire_lock,
    download_to_temp,
    list_objects,
    move_object,
    release_lock,
    upload_bytes,
)
from .model import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    load_model,
    process_image,
    process_video,
)

# Config from env
INGEST_PREFIX = os.environ.get("S3_INGEST_PREFIX", "ingest/")
PROCESSED_PREFIX = os.environ.get("S3_PROCESSED_PREFIX", "processed/")
CROPS_PREFIX = os.environ.get("S3_CROPS_PREFIX", "crops/")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
CONFIDENCE = float(os.environ.get("CONFIDENCE", "0.25"))
FRAME_SKIP = int(os.environ.get("FRAME_SKIP", "4"))
CATALOG_URL = os.environ.get("CATALOG_URL", "http://catalog:8001")
LOCK_TTL = int(os.environ.get("LOCK_TTL", "300"))

# Unique worker ID
WORKER_ID = f"{platform.node()}-{uuid.uuid4().hex[:8]}"

# Worker state
status = {
    "state": "starting",
    "worker_id": WORKER_ID,
    "current_file": None,
    "files_processed": 0,
    "total_detections": 0,
}


def post_sighting(sighting):
    """Post a sighting to the catalog service."""
    try:
        resp = requests.post(f"{CATALOG_URL}/sightings", json=sighting, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  Warning: failed to post sighting: {e}")
        return None


def save_crop(crop, source_key, index, timestamp=None):
    """Encode crop as JPEG and upload to S3. Returns the S3 key."""
    _, encoded = cv2.imencode(".jpg", crop)
    stem = Path(source_key).stem
    if timestamp is not None:
        crop_key = f"{CROPS_PREFIX}{stem}_{timestamp:.1f}s_{index}.jpg"
    else:
        crop_key = f"{CROPS_PREFIX}{stem}_{index}.jpg"
    upload_bytes(encoded.tobytes(), crop_key, content_type="image/jpeg")
    return crop_key


def process_file(key, model):
    """Download a file from S3, run detection, post results, move to processed."""
    ext = Path(key).suffix.lower()
    if ext not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
        print(f"  Skipping unsupported file: {key}")
        return

    status["current_file"] = key
    print(f"Processing: {key}")

    local_path = download_to_temp(key)

    try:
        if ext in IMAGE_EXTENSIONS:
            image, detections = process_image(local_path, model, CONFIDENCE)
            if image is None:
                print(f"  Could not read image: {key}")
                return

            print(f"  Found {len(detections)} animal(s)")
            for i, det in enumerate(detections, 1):
                crop_key = save_crop(det["crop"], key, i)
                post_sighting(
                    {
                        "animal": det["animal"],
                        "confidence": round(det["confidence"], 4),
                        "bbox": det["bbox"],
                        "source_key": key,
                        "crop_key": crop_key,
                    }
                )
                status["total_detections"] += 1

        else:
            frame_detections = 0
            for result in process_video(local_path, model, CONFIDENCE, FRAME_SKIP):
                if result["type"] == "info":
                    print(
                        f"  Video: {result['total_frames']} frames, {result['fps']:.0f} fps, every {result['skip']} frames"
                    )
                    continue

                for i, det in enumerate(result["detections"], 1):
                    crop_key = save_crop(det["crop"], key, i, result["timestamp"])
                    post_sighting(
                        {
                            "animal": det["animal"],
                            "confidence": round(det["confidence"], 4),
                            "bbox": det["bbox"],
                            "source_key": key,
                            "crop_key": crop_key,
                            "frame_timestamp": round(result["timestamp"], 2),
                        }
                    )
                    frame_detections += 1
                    status["total_detections"] += 1

            print(f"  Found {frame_detections} detection(s) across video")

    finally:
        local_path.unlink(missing_ok=True)

    # Move to processed
    dest_key = key.replace(INGEST_PREFIX, PROCESSED_PREFIX, 1)
    move_object(key, dest_key)
    print(f"  Moved to {dest_key}")

    status["files_processed"] += 1
    status["current_file"] = None


def poll_loop(model):
    """Main polling loop — check for new files in ingest prefix."""
    status["state"] = "idle"
    print(f"Watching s3://{INGEST_PREFIX} every {POLL_INTERVAL}s")
    print(f"  confidence={CONFIDENCE}, frame_skip={FRAME_SKIP}")
    print(f"  catalog={CATALOG_URL}")

    while True:
        try:
            keys = list_objects(INGEST_PREFIX)
            for key in keys:
                # Skip "directory" markers
                if key.endswith("/"):
                    continue
                status["state"] = "processing"
                process_file(key, model)
                status["state"] = "idle"
        except Exception as e:
            print(f"Poll error: {e}")
            status["state"] = "error"

        time.sleep(POLL_INTERVAL)


def start_worker():
    """Load model and start the polling loop."""
    print("Starting detection worker...")
    model, device = load_model()
    print(f"YOLOv8m loaded on {device}")
    poll_loop(model)
