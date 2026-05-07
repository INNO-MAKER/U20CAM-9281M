#!/usr/bin/env python3
"""
Minimal Example: Capture 120fps Video with Manual Exposure on macOS
====================================================================

This is the simplest possible example showing how to:
  1. Set manual exposure via uvc-util before opening the camera
  2. Use OpenCV to capture 120fps video on macOS

This matches the customer's reported workflow:
  "Capturing 120fps videos works fine using my Python codes.
   My current issues are on setting Exposure Time."

Prerequisites on macOS:
  brew install uvc-util
  pip3 install opencv-python

Usage:
  python3 minimal_120fps_with_exposure.py
"""

import cv2
import subprocess
import time

# ---- Configuration ----
CAMERA_INDEX = 0          # macOS camera index
EXPOSURE_MS = 5.0         # 5 ms exposure (good for 120fps, max would be ~8.3ms)
WIDTH = 1280
HEIGHT = 800
FPS = 120
DURATION_SEC = 10
OUTPUT_FILE = "output_120fps.mp4"


def set_manual_exposure_uvc_util(camera_index, exposure_ms):
    """
    Set manual exposure via uvc-util.
    Exposure unit on UVC is 100us, so multiply ms by 10.
    """
    exposure_uvc = int(round(exposure_ms * 10))

    # Step 1: switch to manual exposure mode
    subprocess.run(
        ["uvc-util", "-I", str(camera_index),
         "-s", "auto-exposure-mode=1"],
        check=True
    )

    # Step 2: set exposure time
    subprocess.run(
        ["uvc-util", "-I", str(camera_index),
         "-s", f"exposure-time-abs={exposure_uvc}"],
        check=True
    )

    # Step 3: read back to verify
    result = subprocess.run(
        ["uvc-util", "-I", str(camera_index),
         "-g", "exposure-time-abs"],
        capture_output=True, text=True
    )
    print(f"[uvc-util] exposure-time-abs = {result.stdout.strip()}")
    print(f"[uvc-util] target was {exposure_uvc} ({exposure_ms} ms)")


def main():
    # ---- 1. Set exposure BEFORE opening with OpenCV ----
    print(f"Setting manual exposure to {EXPOSURE_MS} ms...")
    set_manual_exposure_uvc_util(CAMERA_INDEX, EXPOSURE_MS)
    time.sleep(0.5)  # let the camera apply the new setting

    # ---- 2. Open camera with OpenCV (your existing 120fps code) ----
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"ERROR: cannot open camera {CAMERA_INDEX}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Opened: {actual_w}x{actual_h} @ {actual_fps:.1f}fps")

    # ---- 3. Setup video writer ----
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(OUTPUT_FILE, fourcc, FPS, (actual_w, actual_h))

    # ---- 4. Capture loop ----
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

    # ---- 5. Cleanup ----
    cap.release()
    writer.release()


if __name__ == "__main__":
    main()
