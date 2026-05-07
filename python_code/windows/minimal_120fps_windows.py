#!/usr/bin/env python3
"""
Minimal Example: 120fps Capture with Manual Exposure on Windows
================================================================

Uses OpenCV with DirectShow backend (CAP_DSHOW) to capture 120fps video
from U20CAM-9281M with manual exposure control.

IMPORTANT - Windows-specific points:
  1. MUST use cv2.CAP_DSHOW backend (default MSMF backend has poor UVC support)
  2. Exposure value uses log2(seconds), NOT UVC 100us units
  3. AUTO_EXPOSURE: 0.25 = manual, 0.75 = auto

Prerequisites:
  pip install opencv-python

Usage:
  python minimal_120fps_with_exposure.py
"""

import cv2
import math
import time

# ---- Configuration ----
CAMERA_INDEX = 0
EXPOSURE_MS = 5.0          # 5 ms exposure (good for 120fps)
WIDTH = 1280
HEIGHT = 800
FPS = 120
DURATION_SEC = 10
OUTPUT_FILE = "output_120fps.mp4"


def ms_to_log2(exposure_ms):
    """Convert ms to DirectShow log2-seconds exposure value."""
    return round(math.log2(exposure_ms / 1000.0))


def main():
    # ---- Open camera with DirectShow backend ----
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera {CAMERA_INDEX}")
        return

    # ---- Set manual exposure mode (DirectShow: 0.25 = manual) ----
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)

    # ---- Set exposure value (log2 seconds) ----
    log2_value = ms_to_log2(EXPOSURE_MS)
    cap.set(cv2.CAP_PROP_EXPOSURE, log2_value)
    print(f"Exposure: target {EXPOSURE_MS} ms -> log2 {log2_value}")
    print(f"Verify:   CAP_PROP_EXPOSURE = {cap.get(cv2.CAP_PROP_EXPOSURE)}")

    # ---- Set capture format ----
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Format:   {actual_w}x{actual_h} @ {actual_fps:.1f}fps")

    # ---- Setup video writer ----
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(OUTPUT_FILE, fourcc, FPS, (actual_w, actual_h))

    # ---- Capture loop ----
    print(f"Recording {DURATION_SEC}s to {OUTPUT_FILE}...")
    t0 = time.time()
    n = 0
    while time.time() - t0 < DURATION_SEC:
        ret, frame = cap.read()
        if not ret:
            print("WARN: frame read failed")
            break
        writer.write(frame)
        n += 1

    elapsed = time.time() - t0
    measured_fps = n / elapsed if elapsed > 0 else 0
    print(f"Captured {n} frames in {elapsed:.2f}s ({measured_fps:.1f} fps actual)")

    # ---- Cleanup ----
    cap.release()
    writer.release()


if __name__ == "__main__":
    main()
