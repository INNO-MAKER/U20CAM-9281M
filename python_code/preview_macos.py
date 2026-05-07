#!/usr/bin/env python3
"""
U20CAM-9281M Live Preview - macOS
==================================

Standalone preview window for U20CAM-9281M on macOS.

Features:
  - Live preview with on-screen FPS / resolution / exposure overlay
  - Hotkeys: q=quit, s=save snapshot, +/-=adjust exposure, [/]=adjust gain
  - Uses uvc-util for reliable exposure/gain control on macOS

IMPORTANT - macOS specifics:
  - OpenCV's AVFoundation backend has poor UVC control support
  - Exposure/gain control is done via uvc-util (separate command-line tool)
  - Exposure unit is UVC standard (100us each, same as Linux)

Requirements:
  brew install uvc-util
  pip3 install opencv-python numpy

Usage:
  python3 preview_macos.py                              # camera index 0
  python3 preview_macos.py -c 1                         # camera index 1
  python3 preview_macos.py --width 1280 --height 800 --fps 120
  python3 preview_macos.py --exposure-ms 5 --gain 32    # set at start
"""

import argparse
import subprocess
import shutil
import sys
import os
import time

try:
    import cv2
except ImportError:
    print("[ERROR] OpenCV not installed. pip3 install opencv-python")
    sys.exit(1)


# ============================================================
# uvc-util helpers
# ============================================================

def has_uvc_util():
    return shutil.which("uvc-util") is not None


def uvc_set(camera_index, ctrl_name, value):
    """Set a UVC control via uvc-util."""
    if not has_uvc_util():
        return False
    try:
        result = subprocess.run(
            ["uvc-util", "-I", str(camera_index),
             "-s", f"{ctrl_name}={value}"],
            capture_output=True, text=True, timeout=3
        )
        return result.returncode == 0
    except Exception:
        return False


def uvc_get(camera_index, ctrl_name):
    if not has_uvc_util():
        return None
    try:
        result = subprocess.run(
            ["uvc-util", "-I", str(camera_index),
             "-g", ctrl_name],
            capture_output=True, text=True, timeout=3
        )
        return result.stdout.strip()
    except Exception:
        return None


def set_manual_exposure(camera_index, exposure_ms):
    """Switch to manual exposure mode and set value."""
    uvc_set(camera_index, "auto-exposure-mode", 1)
    uvc_value = int(round(exposure_ms * 10))
    uvc_set(camera_index, "exposure-time-abs", uvc_value)
    return uvc_value


def set_auto_exposure(camera_index):
    """Restore auto exposure mode (aperture priority)."""
    uvc_set(camera_index, "auto-exposure-mode", 8)


def set_gain(camera_index, gain_value):
    uvc_set(camera_index, "gain", gain_value)


# ============================================================
# Preview Loop
# ============================================================

def run_preview(camera_index, width, height, fps, exposure_ms=None, gain=None):
    if not has_uvc_util():
        print("[WARN] uvc-util not found - exposure/gain control will NOT work.")
        print("       Install with: brew install uvc-util")
        print("       Continuing with preview only.")
        print()

    # Apply initial settings via uvc-util BEFORE opening with OpenCV
    if exposure_ms is not None:
        uvc_value = set_manual_exposure(camera_index, exposure_ms)
        print(f"[Init] Exposure: {exposure_ms} ms (UVC {uvc_value})")

    if gain is not None:
        set_gain(camera_index, gain)
        print(f"[Init] Gain: {gain}")

    # Small delay so the camera applies the settings
    time.sleep(0.3)

    # Open camera with OpenCV
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open camera {camera_index}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"[Open] camera {camera_index}: {actual_w}x{actual_h} @ {actual_fps:.1f}fps")
    print()
    print("Hotkeys:")
    print("  q       quit")
    print("  s       save snapshot to ./snapshots/")
    print("  + / -   exposure +/- 1ms")
    print("  ] / [   gain +/- 4")
    print("  a       toggle auto/manual exposure")
    print()

    os.makedirs("snapshots", exist_ok=True)

    current_exp_ms = exposure_ms if exposure_ms else 5.0
    current_gain = gain if gain is not None else 0
    auto_exp = exposure_ms is None

    frame_count = 0
    fps_t0 = time.time()
    measured_fps = 0.0

    win_name = "U20CAM-9281M Preview (macOS)"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[WARN] Frame read failed")
            time.sleep(0.05)
            continue

        frame_count += 1
        elapsed = time.time() - fps_t0
        if elapsed >= 1.0:
            measured_fps = frame_count / elapsed
            frame_count = 0
            fps_t0 = time.time()

        # Overlay
        h, w = frame.shape[:2]
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 70), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

        mode_str = "AUTO" if auto_exp else "MANUAL"
        info1 = f"{w}x{h}  {measured_fps:.1f} fps"
        info2 = f"Exp: {current_exp_ms:.1f}ms ({mode_str})  Gain: {current_gain}"
        cv2.putText(frame, info1, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
        cv2.putText(frame, info2, (10, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)

        cv2.imshow(win_name, frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('s'):
            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = f"snapshots/snap_{ts}.png"
            cv2.imwrite(fname, frame)
            print(f"[Save] {fname}")
        elif key == ord('+') or key == ord('='):
            current_exp_ms = min(33.0, current_exp_ms + 1.0)
            set_manual_exposure(camera_index, current_exp_ms)
            auto_exp = False
            print(f"[Exp] {current_exp_ms:.1f} ms")
        elif key == ord('-') or key == ord('_'):
            current_exp_ms = max(0.1, current_exp_ms - 1.0)
            set_manual_exposure(camera_index, current_exp_ms)
            auto_exp = False
            print(f"[Exp] {current_exp_ms:.1f} ms")
        elif key == ord(']'):
            current_gain = min(64, current_gain + 4)
            set_gain(camera_index, current_gain)
            print(f"[Gain] {current_gain}")
        elif key == ord('['):
            current_gain = max(0, current_gain - 4)
            set_gain(camera_index, current_gain)
            print(f"[Gain] {current_gain}")
        elif key == ord('a'):
            if auto_exp:
                set_manual_exposure(camera_index, current_exp_ms)
                auto_exp = False
                print("[Mode] MANUAL exposure")
            else:
                set_auto_exposure(camera_index)
                auto_exp = True
                print("[Mode] AUTO exposure")

    cap.release()
    cv2.destroyAllWindows()
    print("[Done]")


def main():
    p = argparse.ArgumentParser(description="U20CAM-9281M live preview (macOS)")
    p.add_argument("-c", "--camera", type=int, default=0,
                   help="Camera index (default: 0)")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=800)
    p.add_argument("--fps", type=int, default=120)
    p.add_argument("--exposure-ms", type=float, default=None,
                   help="Initial exposure in ms (default: auto)")
    p.add_argument("--gain", type=int, default=None,
                   help="Initial gain value")
    args = p.parse_args()

    run_preview(args.camera, args.width, args.height, args.fps,
                args.exposure_ms, args.gain)


if __name__ == "__main__":
    main()
