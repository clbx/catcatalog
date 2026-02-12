"""Detection worker — polls S3 for new clips, runs detection, posts results to catalog."""

import os
import platform
import threading
import time
import uuid
from pathlib import Path

import cv2
import requests

from ..storage import (
    download_to_temp,
    get_bucket,
    list_objects,
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
S3_WATCH_PREFIX = os.environ.get("S3_WATCH_PREFIX", "clips/")
CROPS_PREFIX = os.environ.get("S3_CROPS_PREFIX", "crops/")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
CONFIDENCE = float(os.environ.get("CONFIDENCE", "0.25"))
FRAME_SKIP = int(os.environ.get("FRAME_SKIP", "4"))
CATALOG_URL = os.environ.get("CATALOG_URL", "http://catalog:8001")

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


def try_lock(key):
    """Try to lock a clip for processing via the catalog API.
    Returns True if lock acquired, False if already processed/in-progress."""
    try:
        resp = requests.post(
            f"{CATALOG_URL}/clips/lock",
            json={"source_key": key, "worker_id": WORKER_ID},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("locked", False)
    except Exception as e:
        print(f"  Warning: lock request failed for {key}: {e}")
    return False


def mark_complete(key, detections, error=None):
    """Mark a clip as done or errored in the catalog."""
    try:
        payload = {"source_key": key, "detections": detections}
        if error:
            payload["error"] = str(error)
        resp = requests.post(f"{CATALOG_URL}/clips/complete", json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Warning: failed to mark complete for {key}: {e}")


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
    """Download a file from S3, run detection, post one sighting with best crop."""
    ext = Path(key).suffix.lower()
    if ext not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
        return

    status["current_file"] = key
    print(f"Processing: {key}")

    local_path = download_to_temp(key)
    all_detections = []

    try:
        if ext in IMAGE_EXTENSIONS:
            image, detections = process_image(local_path, model, CONFIDENCE)
            if image is None:
                print(f"  Could not read image: {key}")
                mark_complete(key, 0, error="Could not read image")
                return

            for i, det in enumerate(detections, 1):
                crop_key = save_crop(det["crop"], key, i)
                all_detections.append(
                    {
                        "confidence": det["confidence"],
                        "crop_key": crop_key,
                        "frame_timestamp": None,
                    }
                )

        else:
            for result in process_video(local_path, model, CONFIDENCE, FRAME_SKIP):
                if result["type"] == "info":
                    print(
                        f"  Video: {result['total_frames']} frames, {result['fps']:.0f} fps, every {result['skip']} frames"
                    )
                    continue

                for i, det in enumerate(result["detections"], 1):
                    crop_key = save_crop(det["crop"], key, i, result["timestamp"])
                    all_detections.append(
                        {
                            "confidence": det["confidence"],
                            "crop_key": crop_key,
                            "frame_timestamp": round(result["timestamp"], 2),
                        }
                    )

        print(f"  {len(all_detections)} detection(s)")

        if all_detections:
            # Pick the best detection (highest confidence) for the sighting
            best = max(all_detections, key=lambda d: d["confidence"])
            post_sighting(
                {
                    "confidence": round(best["confidence"], 4),
                    "source_key": key,
                    "crop_key": best["crop_key"],
                    "frame_timestamp": best["frame_timestamp"],
                }
            )
            status["total_detections"] += 1

        mark_complete(key, len(all_detections))

    except Exception as e:
        print(f"  Error processing {key}: {e}")
        mark_complete(key, 0, error=str(e))

    finally:
        local_path.unlink(missing_ok=True)

    status["files_processed"] += 1
    status["current_file"] = None


def poll_loop(model):
    """Main polling loop — check for new files, lock and process new ones."""
    status["state"] = "idle"
    endpoint = os.environ.get("S3_ENDPOINT_URL", "s3.amazonaws.com")
    bucket = get_bucket()
    print(f"Watching {endpoint}/{bucket}/{S3_WATCH_PREFIX} every {POLL_INTERVAL}s")
    print(f"  confidence={CONFIDENCE}, frame_skip={FRAME_SKIP}")
    print(f"  catalog={CATALOG_URL}")

    known_keys = set()

    while True:
        try:
            keys = list_objects(S3_WATCH_PREFIX)
            for key in keys:
                if key.endswith("/"):
                    continue
                if key in known_keys:
                    continue
                if not try_lock(key):
                    known_keys.add(key)
                    continue
                status["state"] = "processing"
                process_file(key, model)
                known_keys.add(key)
                status["state"] = "idle"
        except Exception as e:
            print(f"Poll error: {e}")
            status["state"] = "error"

        time.sleep(POLL_INTERVAL)


def start_worker():
    """Load model and start the polling loop."""
    print(f"Starting detection worker (version: {os.environ.get('VERSION', 'dev')})")
    model, device = load_model()
    print(f"YOLOv8m loaded on {device}")
    poll_loop(model)
