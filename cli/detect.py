#!/usr/bin/env python3
"""CLI tool for animal detection on images and video."""

import argparse
import sys
from pathlib import Path

# Add project root to path so services can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from services.detect import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    annotate_frame,
    load_model,
    process_image,
    process_video,
)


def handle_image(path, model, args):
    """Process a single image and print results."""
    image, detections = process_image(path, model, args.confidence)

    if image is None:
        print(f"Error: Could not read image {path}", file=sys.stderr)
        return

    if not detections:
        print("No animals detected.")
        return

    print(f"\nFound {len(detections)} animal(s):\n")
    for i, det in enumerate(detections, 1):
        x1, y1, x2, y2 = det["bbox"]
        print(f"  {det['animal'].title()} {i}:")
        print(f"    Confidence: {det['confidence']:.1%}")
        print(f"    Bounding box: ({x1}, {y1}) -> ({x2}, {y2})")

        if args.save_crops:
            crop_dir = Path("crops")
            crop_dir.mkdir(exist_ok=True)
            crop_path = crop_dir / f"{path.stem}_{det['animal']}_{i}.jpg"
            cv2.imwrite(str(crop_path), det["crop"])
            print(f"    Crop saved: {crop_path}")

    if args.annotate:
        out_path = Path(f"annotated_{path.name}")
        cv2.imwrite(str(out_path), annotate_frame(image, detections))
        print(f"\nAnnotated image saved: {out_path}")


def handle_video(path, model, args):
    """Process a video and print results."""
    total_detections = 0
    writer = None

    for result in process_video(
        path, model, args.confidence, args.frame_skip, args.every
    ):
        if result["type"] == "info":
            print(
                f"  Video: {result['total_frames']} frames, {result['fps']:.1f} fps, {result['duration']:.1f}s"
            )
            print(f"  Checking every {result['skip']} frame(s)\n")
            info = result
            continue

        detections = result["detections"]
        timestamp = result["timestamp"]
        frame = result["frame"]

        if detections:
            total_detections += len(detections)
            summary = ", ".join(
                f"{det['animal']}({det['confidence']:.0%})" for det in detections
            )
            print(f"  [{timestamp:6.1f}s] {len(detections)} animal(s): {summary}")

            if args.save_crops:
                crop_dir = Path("crops")
                crop_dir.mkdir(exist_ok=True)
                for i, det in enumerate(detections, 1):
                    crop_path = (
                        crop_dir
                        / f"{path.stem}_{timestamp:.1f}s_{det['animal']}_{i}.jpg"
                    )
                    cv2.imwrite(str(crop_path), det["crop"])

        if args.annotate:
            if writer is None:
                out_path = Path(f"annotated_{path.stem}.mp4")
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                h, w = frame.shape[:2]
                writer = cv2.VideoWriter(
                    str(out_path),
                    fourcc,
                    info["fps"] / info["skip"],
                    (w, h),
                )
            writer.write(annotate_frame(frame, detections))

    if writer:
        writer.release()
        print(f"\nAnnotated video saved: {out_path}")

    if total_detections == 0:
        print("  No animals detected in any frame.")
    else:
        print(f"\n  Total detections across all frames: {total_detections}")
        if args.save_crops:
            print(f"  Crops saved to: crops/")


def main():
    parser = argparse.ArgumentParser(description="Detect animals in images and video")
    parser.add_argument("input", type=Path, help="Path to an image or video file")
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.25,
        help="Minimum detection confidence (default: 0.25)",
    )
    parser.add_argument(
        "--save-crops",
        action="store_true",
        help="Save cropped animal images to ./crops/",
    )
    parser.add_argument(
        "--annotate",
        action="store_true",
        help="Save annotated output with bounding boxes",
    )
    parser.add_argument(
        "--every",
        type=float,
        default=1.0,
        help="For video: process one frame every N seconds (default: 1.0)",
    )
    parser.add_argument(
        "--frame-skip",
        type=int,
        default=None,
        help="For video: process every Nth frame (overrides --every)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    model, device = load_model()
    print(f"Loading YOLOv8m on {device}...")

    ext = args.input.suffix.lower()
    print(f"Processing: {args.input}")

    if ext in IMAGE_EXTENSIONS:
        handle_image(args.input, model, args)
    elif ext in VIDEO_EXTENSIONS:
        handle_video(args.input, model, args)
    else:
        print(f"Error: Unsupported file type '{ext}'", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
