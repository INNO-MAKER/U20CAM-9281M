#!/usr/bin/env python3
"""
U20CAM-9281M Live Preview - Linux
==================================

Standalone preview window for U20CAM-9281M on Linux.

Features:
  - Live preview with on-screen FPS / resolution / exposure overlay
  - Hotkeys: q=quit, s=save snapshot, +/-=adjust exposure, [/]=adjust gain
  - Auto-detects camera device

Requirements:
  sudo apt install v4l-utils python3-opencv
  pip3 install opencv-python numpy

Usage:
  python3 preview_linux.py                              # auto-detect
  python3 preview_linux.py -d /dev/video0               # specify device
  python3 preview_linux.py --width 1280 --height 800 --fps 120
  python3 preview_linux.py --exposure-ms 5 --gain 32    # set exposure/gain at start
"""

import argparse
import subprocess
import sys
import os
import re
import time

try:
    import cv2
except ImportError:
    print("[ERROR] OpenCV not installed. sudo apt install python3-opencv")
    sys.exit(1)


# ============================================================
# v4l2-ctl helpers
# ============================================================

CTRL_AE = ["auto_exposure", "exposure_auto"]
CTRL_EXP = ["exposure_time_absolute", "exposure_absolute"]
CTRL_GAIN = "gain"
AE_MANUAL = 1


def detect_camera():
    try:
        out = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            capture_output=True, text=True, timeout=5
        ).stdout
    except FileNotFoundError:
        return "/dev/video0"

    current_name = None
    for line in out.splitlines():
        if line and not line.startswith("\t"):
            current_name = line.strip()
        elif line.startswith("\t/dev/video"):
            path = line.strip()
            if current_name and re.search(r"U20CAM|OV9281|InnoMaker|9281",
                                          current_name, re.IGNORECASE):
                print(f"[Detect] Found {current_name} -> {path}")
                return path

    if os.path.exists("/dev/video0"):
        return "/dev/video0"
    return None


def find_ctrl(device, candidates):
    try:
        out = subprocess.run(
            ["v4l2-ctl", "-d", device, "-l"],
            capture_output=True, text=True, timeout=3
        ).stdout
        for name in candidates:
            if name in out:
                return name
    except Exception:
        pass
    return None


def set_ctrl(device, name, value):
    if not name:
        return False
    try:
        result = subprocess.run(
            ["v4l2-ctl", "-d", device, "-c", f"{name}={value}"],
            capture_output=True, text=True, timeout=3
        )
        return result.returncode == 0
    except Exception:
        return False


def get_ctrl(device, name):
    if not name:
        return None
    try:
        result = subprocess.run(
            ["v4l2-ctl", "-d", device, "-C", name],
            capture_output=True, text=True, timeout=3
        )
        if ":" in result.stdout:
            return result.stdout.split(":")[1].strip()
    except Exception:
        pass
    return None


# ============================================================
# Preview Loop
# ============================================================

def run_preview(device, width, height, fps, exposure_ms=None, gain=None):
    # Resolve control names
    ctrl_ae = find_ctrl(device, CTRL_AE)
    ctrl_exp = find_ctrl(device, CTRL_EXP)

    # Apply initial exposure/gain if requested
    if exposure_ms is not None and ctrl_ae and ctrl_exp:
        set_ctrl(device, ctrl_ae, AE_MANUAL)
        uvc_value = int(round(exposure_ms * 10))
        set_ctrl(device, ctrl_exp, uvc_value)
        print(f"[Init] Exposure: {exposure_ms} ms (UVC {uvc_value})")

    if gain is not None:
        set_ctrl(device, CTRL_GAIN, gain)
        print(f"[Init] Gain: {gain}")

    # Open camera
    m = re.search(r"/dev/video(\d+)", device)
    cam_idx = int(m.group(1)) if m else 0

    cap = cv2.VideoCapture(cam_idx, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open {device}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"[Open] {actual_w}x{actual_h} @ {actual_fps:.1f}fps requested")
    print()
    print("Hotkeys:")
    print("  q       quit")
    print("  s       save snapshot to ./snapshots/")
    print("  + / -   exposure +/- 1ms")
    print("  ] / [   gain +/- 4")
    print("  a       toggle auto/manual exposure")
    print()

    os.makedirs("snapshots", exist_ok=True)

    # Track current settings
    current_exp_ms = exposure_ms if exposure_ms else 5.0
    current_gain = gain if gain is not None else 0
    auto_exp = exposure_ms is None

    # FPS measurement
    frame_count = 0
    fps_t0 = time.time()
    measured_fps = 0.0

    win_name = "U20CAM-9281M Preview (Linux)"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[WARN] Frame read failed")
            time.sleep(0.05)
            continue

        # FPS calc
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
            uvc = int(round(current_exp_ms * 10))
            set_ctrl(device, ctrl_ae, AE_MANUAL)
            set_ctrl(device, ctrl_exp, uvc)
            auto_exp = False
            print(f"[Exp] {current_exp_ms:.1f} ms")
        elif key == ord('-') or key == ord('_'):
            current_exp_ms = max(0.1, current_exp_ms - 1.0)
            uvc = int(round(current_exp_ms * 10))
            set_ctrl(device, ctrl_ae, AE_MANUAL)
            set_ctrl(device, ctrl_exp, uvc)
            auto_exp = False
            print(f"[Exp] {current_exp_ms:.1f} ms")
        elif key == ord(']'):
            current_gain = min(64, current_gain + 4)
            set_ctrl(device, CTRL_GAIN, current_gain)
            print(f"[Gain] {current_gain}")
        elif key == ord('['):
            current_gain = max(0, current_gain - 4)
            set_ctrl(device, CTRL_GAIN, current_gain)
            print(f"[Gain] {current_gain}")
        elif key == ord('a'):
            if auto_exp:
                set_ctrl(device, ctrl_ae, AE_MANUAL)
                auto_exp = False
                print("[Mode] MANUAL exposure")
            else:
                set_ctrl(device, ctrl_ae, 3)
                auto_exp = True
                print("[Mode] AUTO exposure")

    cap.release()
    cv2.destroyAllWindows()
    print("[Done]")


def main():
    p = argparse.ArgumentParser(description="U20CAM-9281M live preview (Linux)")
    p.add_argument("-d", "--device", default=None,
                   help="Camera device (default: auto-detect)")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=800)
    p.add_argument("--fps", type=int, default=120)
    p.add_argument("--exposure-ms", type=float, default=None,
                   help="Initial exposure in ms (default: auto)")
    p.add_argument("--gain", type=int, default=None,
                   help="Initial gain value")
    args = p.parse_args()

    device = args.device or detect_camera()
    if not device or not os.path.exists(device):
        print(f"[ERROR] Camera not found: {device}")
        sys.exit(1)

    run_preview(device, args.width, args.height, args.fps,
                args.exposure_ms, args.gain)


if __name__ == "__main__":
    main()
