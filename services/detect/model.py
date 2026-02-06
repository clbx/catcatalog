"""Core animal detection logic using YOLOv8."""

from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

ANIMAL_CLASSES = {
    15: "cat",
    16: "dog",
    21: "bear",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".m4v"}

ANNOTATION_COLORS = {
    "cat": (0, 255, 0),
    "dog": (255, 150, 0),
    "bear": (0, 0, 255),
}


def get_device():
    """Auto-detect the best available device."""
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model(model_path="yolov8m.pt", device=None):
    """Load YOLOv8 model on the best available device."""
    if device is None:
        device = get_device()
    model = YOLO(model_path)
    model.to(device)
    return model, device


def detect_frame(frame, model, confidence=0.25):
    """Run animal detection on a single frame (numpy array, BGR).

    Returns list of dicts with keys: bbox, confidence, crop, animal
    """
    results = model(frame, verbose=False, conf=confidence)[0]
    detections = []

    for box in results.boxes:
        class_id = int(box.cls[0])
        conf = float(box.conf[0])

        if class_id not in ANIMAL_CLASSES:
            continue

        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        crop = frame[y1:y2, x1:x2]
        detections.append(
            {
                "bbox": [x1, y1, x2, y2],
                "confidence": conf,
                "crop": crop,
                "animal": ANIMAL_CLASSES[class_id],
            }
        )

    return detections


def annotate_frame(frame, detections):
    """Draw bounding boxes and labels on a frame. Returns a copy."""
    annotated = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        color = ANNOTATION_COLORS.get(det["animal"], (255, 255, 255))
        label = f"{det['animal'].title()}: {det['confidence']:.0%}"
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            annotated,
            label,
            (x1, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
        )
    return annotated


def process_image(path, model, confidence=0.25):
    """Detect animals in an image file.

    Returns (image, detections) or (None, None) if the image can't be read.
    """
    image = cv2.imread(str(path))
    if image is None:
        return None, None
    return image, detect_frame(image, model, confidence)


def process_video(path, model, confidence=0.25, frame_skip=None, every=1.0):
    """Detect animals in a video file.

    Yields (frame_num, timestamp, frame, detections) for each processed frame.
    """
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps

    if frame_skip:
        skip = frame_skip
    else:
        skip = max(1, int(fps * every))

    yield {
        "type": "info",
        "fps": fps,
        "total_frames": total_frames,
        "duration": duration,
        "skip": skip,
    }

    frame_num = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_num % skip != 0:
                frame_num += 1
                continue

            timestamp = frame_num / fps
            detections = detect_frame(frame, model, confidence)

            yield {
                "type": "frame",
                "frame_num": frame_num,
                "timestamp": timestamp,
                "frame": frame,
                "detections": detections,
            }

            frame_num += 1
    finally:
        cap.release()
