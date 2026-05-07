#!/usr/bin/env python3
"""
U20CAM-9281M Live Preview - Windows
====================================

Standalone preview window for U20CAM-9281M on Windows using OpenCV
DirectShow backend.

Features:
  - Live preview with on-screen FPS / resolution / exposure overlay
  - Hotkeys: q=quit, s=save snapshot, +/-=adjust exposure, [/]=adjust gain
  - Uses CAP_DSHOW backend for proper UVC control support

IMPORTANT - Windows specifics:
  - MUST use CAP_DSHOW backend (default MSMF has poor UVC control support)
  - Exposure uses log2(seconds), NOT UVC 100us units
  - AUTO_EXPOSURE: 0.25 = manual, 0.75 = auto

Requirements:
  pip install opencv-python numpy

Usage:
  python preview_windows.py                                # camera index 0
  python preview_windows.py -c 1                           # camera index 1
  python preview_windows.py --width 1280 --height 800 --fps 120
  python preview_windows.py --exposure-ms 5 --gain 32      # set at start
"""

import argparse
import math
import sys
import os
import time

try:
    import cv2
except ImportError:
    print("[ERROR] OpenCV not installed. pip install opencv-python")
    sys.exit(1)


# ============================================================
# Exposure conversion (log2 seconds <-> milliseconds)
# ============================================================

def ms_to_log2(exposure_ms):
    if exposure_ms <= 0:
        return -13
    return round(math.log2(exposure_ms / 1000.0))


def log2_to_ms(log2_value):
    return (2 ** log2_value) * 1000.0


# ============================================================
# Preview Loop
# ============================================================

def run_preview(camera_index, width, height, fps, exposure_ms=None, gain=None):
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open camera {camera_index} with DirectShow")
        return

    # Apply initial settings
    if exposure_ms is not None:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # manual
        log2_val = ms_to_log2(exposure_ms)
        cap.set(cv2.CAP_PROP_EXPOSURE, log2_val)
        actual_ms = log2_to_ms(log2_val)
        print(f"[Init] Exposure: target {exposure_ms}ms -> log2 {log2_val} "
              f"(actual ~{actual_ms:.2f}ms)")

    if gain is not None:
        cap.set(cv2.CAP_PROP_GAIN, gain)
        print(f"[Init] Gain: {gain}")

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
    print("  s       save snapshot to .\\snapshots\\")
    print("  + / -   exposure log2 step +/- 1")
    print("  ] / [   gain +/- 4")
    print("  a       toggle auto/manual exposure")
    print()

    os.makedirs("snapshots", exist_ok=True)

    # Track current state
    current_log2 = ms_to_log2(exposure_ms) if exposure_ms else -7
    current_exp_ms = log2_to_ms(current_log2)
    current_gain = gain if gain is not None else int(cap.get(cv2.CAP_PROP_GAIN))
    auto_exp = exposure_ms is None

    # FPS measurement
    frame_count = 0
    fps_t0 = time.time()
    measured_fps = 0.0

    win_name = "U20CAM-9281M Preview (Windows)"
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
        info2 = (f"Exp: log2={current_log2} ({current_exp_ms:.2f}ms) "
                 f"[{mode_str}]  Gain: {current_gain}")
        cv2.putText(frame, info1, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
        cv2.putText(frame, info2, (10, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)

        cv2.imshow(win_name, frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('s'):
            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = f"snapshots\\snap_{ts}.png"
            cv2.imwrite(fname, frame)
            print(f"[Save] {fname}")
        elif key == ord('+') or key == ord('='):
            # Decrease log2 = shorter exposure (Windows is inverted)
            # Actually + means longer, so increase log2
            current_log2 = min(-1, current_log2 + 1)
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
            cap.set(cv2.CAP_PROP_EXPOSURE, current_log2)
            current_exp_ms = log2_to_ms(current_log2)
            auto_exp = False
            print(f"[Exp] log2={current_log2} ({current_exp_ms:.2f}ms)")
        elif key == ord('-') or key == ord('_'):
            current_log2 = max(-13, current_log2 - 1)
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
            cap.set(cv2.CAP_PROP_EXPOSURE, current_log2)
            current_exp_ms = log2_to_ms(current_log2)
            auto_exp = False
            print(f"[Exp] log2={current_log2} ({current_exp_ms:.2f}ms)")
        elif key == ord(']'):
            current_gain = min(64, current_gain + 4)
            cap.set(cv2.CAP_PROP_GAIN, current_gain)
            print(f"[Gain] {current_gain}")
        elif key == ord('['):
            current_gain = max(0, current_gain - 4)
            cap.set(cv2.CAP_PROP_GAIN, current_gain)
            print(f"[Gain] {current_gain}")
        elif key == ord('a'):
            if auto_exp:
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
                auto_exp = False
                print("[Mode] MANUAL exposure")
            else:
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
                auto_exp = True
                print("[Mode] AUTO exposure")

    cap.release()
    cv2.destroyAllWindows()
    print("[Done]")


def main():
    p = argparse.ArgumentParser(description="U20CAM-9281M live preview (Windows)")
    p.add_argument("-c", "--camera", type=int, default=0,
                   help="Camera index (default: 0)")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=800)
    p.add_argument("--fps", type=int, default=120)
    p.add_argument("--exposure-ms", type=float, default=None,
                   help="Initial exposure in ms (default: auto)")
    p.add_argument("--gain", type=float, default=None,
                   help="Initial gain value")
    args = p.parse_args()

    run_preview(args.camera, args.width, args.height, args.fps,
                args.exposure_ms, args.gain)


if __name__ == "__main__":
    main()
