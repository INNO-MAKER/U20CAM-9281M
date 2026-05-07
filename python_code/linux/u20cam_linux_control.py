#!/usr/bin/env python3
"""
U20CAM-9281M Universal Control Script for Linux
================================================

Control U20CAM-9281M camera via v4l2-ctl on Linux:
  - Switch between stream mode (free-running) and trigger mode
  - Set manual exposure value in stream mode
  - Set gain value in stream mode
  - Live preview to verify settings

Background:
  U20CAM-9281M uses UVC standard controls. On Linux these are accessible
  via v4l2-ctl. Two operating modes:

    Stream Mode  (default):  camera outputs frames continuously at set FPS
    Trigger Mode:            camera waits for FSIN external pulse to output a frame

  Mode switching is done via the UVC "focus_automatic_continuous" control:
    focus_automatic_continuous = 0  ->  Stream mode
    focus_automatic_continuous = 1  ->  Trigger mode

  Manual exposure requires:
    auto_exposure = 1            (manual mode)
    exposure_time_absolute = N   (UVC units, 100us each)

Exposure Time Unit:
  UVC standard - exposure_time_absolute is in 100us units:
    value 1   = 0.1 ms
    value 50  = 5 ms
    value 83  = 8.3 ms (~120fps max)
    value 100 = 10 ms
    value 200 = 20 ms
    value 333 = 33.3 ms (~30fps max)

Requirements:
  sudo apt install v4l-utils python3-opencv
  pip3 install opencv-python numpy

Usage:
  # Show camera status and available controls
  python3 u20cam_linux_control.py --status

  # Switch to stream mode (free-running)
  python3 u20cam_linux_control.py --mode stream

  # Switch to trigger mode (wait for FSIN)
  python3 u20cam_linux_control.py --mode trigger

  # Stream mode + manual exposure 5ms + gain 32
  python3 u20cam_linux_control.py --mode stream --exposure-ms 5 --gain 32

  # Stream mode + auto exposure
  python3 u20cam_linux_control.py --mode stream --auto-exposure

  # Just set exposure (keep current mode)
  python3 u20cam_linux_control.py --exposure-ms 10

  # Just set gain (keep current mode)
  python3 u20cam_linux_control.py --gain 16

  # Set + preview
  python3 u20cam_linux_control.py --mode stream --exposure-ms 5 --gain 32 --preview

  # Specify camera device
  python3 u20cam_linux_control.py -d /dev/video2 --status
"""

import argparse
import subprocess
import sys
import os
import time
import re


# ============================================================
# v4l2-ctl Control Names
# ============================================================
# Different kernel versions may use slightly different names.
# We try both old and new names.

CTRL_TRIGGER_MODE_CANDIDATES = [
    "focus_automatic_continuous",   # newer kernels (>= 5.10)
    "focus_auto",                    # older kernels
]

CTRL_AUTO_EXPOSURE_CANDIDATES = [
    "auto_exposure",                 # newer kernels
    "exposure_auto",                 # older kernels
]

CTRL_EXPOSURE_VALUE_CANDIDATES = [
    "exposure_time_absolute",        # newer kernels
    "exposure_absolute",             # older kernels
]

CTRL_GAIN = "gain"

# UVC auto_exposure / exposure_auto values:
#   1 = Manual Mode
#   3 = Aperture Priority Mode (default auto)
AE_MANUAL = 1
AE_AUTO = 3


# ============================================================
# Helpers
# ============================================================

def detect_camera():
    """Auto-detect U20CAM-9281M device path."""
    try:
        out = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            capture_output=True, text=True, timeout=5
        ).stdout
    except FileNotFoundError:
        print("[ERROR] v4l2-ctl not found. Install: sudo apt install v4l-utils")
        sys.exit(1)

    # Look for U20CAM, OV9281, or InnoMaker references
    devices = []
    current_name = None
    for line in out.splitlines():
        if line and not line.startswith("\t"):
            current_name = line.strip()
        elif line.startswith("\t/dev/video"):
            devices.append((current_name, line.strip()))

    # Prefer devices matching U20CAM
    for name, path in devices:
        if name and re.search(r"U20CAM|OV9281|InnoMaker|9281", name, re.IGNORECASE):
            print(f"[Detect] Found: {name} -> {path}")
            return path

    # Fallback to /dev/video0
    if os.path.exists("/dev/video0"):
        print("[Detect] U20CAM not explicitly found, using /dev/video0")
        return "/dev/video0"

    print("[ERROR] No camera device found.")
    sys.exit(1)


def list_controls(device):
    """List all v4l2 controls of the device."""
    try:
        out = subprocess.run(
            ["v4l2-ctl", "-d", device, "-l"],
            capture_output=True, text=True, timeout=5
        ).stdout
        return out
    except Exception as e:
        return f"[ERROR] {e}"


def find_control_name(device, candidates):
    """Find which control name (from candidates list) the kernel uses."""
    controls_text = list_controls(device)
    for name in candidates:
        if name in controls_text:
            return name
    return None


def get_control(device, ctrl_name):
    """Get current value of a v4l2 control."""
    try:
        result = subprocess.run(
            ["v4l2-ctl", "-d", device, "-C", ctrl_name],
            capture_output=True, text=True, timeout=5
        )
        # output format: "control_name: 1234"
        if ":" in result.stdout:
            return result.stdout.split(":")[1].strip()
        return None
    except Exception:
        return None


def set_control(device, ctrl_name, value):
    """Set a v4l2 control value."""
    try:
        result = subprocess.run(
            ["v4l2-ctl", "-d", device, "-c", f"{ctrl_name}={value}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            err = result.stderr.strip()
            print(f"  [v4l2-ctl] FAILED: {ctrl_name}={value}: {err}")
            return False
        return True
    except Exception as e:
        print(f"  [v4l2-ctl] ERROR: {e}")
        return False


# ============================================================
# Mode Switching
# ============================================================

def switch_to_stream_mode(device):
    """Switch camera to stream mode (free-running)."""
    ctrl = find_control_name(device, CTRL_TRIGGER_MODE_CANDIDATES)
    if not ctrl:
        print("[WARN] Trigger mode control not found. Camera may not support it.")
        return False
    ok = set_control(device, ctrl, 0)
    if ok:
        print(f"  [Mode] {ctrl}=0 -> STREAM (free-running)")
    return ok


def switch_to_trigger_mode(device):
    """Switch camera to trigger mode (wait for FSIN pulse)."""
    ctrl_trig = find_control_name(device, CTRL_TRIGGER_MODE_CANDIDATES)
    ctrl_ae = find_control_name(device, CTRL_AUTO_EXPOSURE_CANDIDATES)

    if not ctrl_trig:
        print("[WARN] Trigger mode control not found.")
        return False

    # Trigger mode requires manual exposure - set both
    if ctrl_ae:
        set_control(device, ctrl_ae, AE_MANUAL)
        print(f"  [Mode] {ctrl_ae}={AE_MANUAL} (manual exposure required for trigger)")

    ok = set_control(device, ctrl_trig, 1)
    if ok:
        print(f"  [Mode] {ctrl_trig}=1 -> TRIGGER (waiting for FSIN pulse)")
    return ok


# ============================================================
# Exposure Control
# ============================================================

def set_manual_exposure(device, exposure_uvc):
    """Set manual exposure with UVC value (units of 100us)."""
    ctrl_ae = find_control_name(device, CTRL_AUTO_EXPOSURE_CANDIDATES)
    ctrl_exp = find_control_name(device, CTRL_EXPOSURE_VALUE_CANDIDATES)

    if not ctrl_ae or not ctrl_exp:
        print("[ERROR] Exposure controls not found.")
        return False

    # Step 1: switch to manual exposure mode (must be done first!)
    ok1 = set_control(device, ctrl_ae, AE_MANUAL)
    if ok1:
        print(f"  [Exp] {ctrl_ae}={AE_MANUAL} (manual mode)")

    # Step 2: set exposure value
    ok2 = set_control(device, ctrl_exp, exposure_uvc)
    if ok2:
        ms = exposure_uvc / 10.0
        print(f"  [Exp] {ctrl_exp}={exposure_uvc} ({ms:.1f} ms)")

    # Step 3: read back to verify
    actual = get_control(device, ctrl_exp)
    if actual:
        print(f"  [Exp] Verified: {ctrl_exp} = {actual}")

    return ok1 and ok2


def set_auto_exposure(device):
    """Restore auto exposure mode."""
    ctrl_ae = find_control_name(device, CTRL_AUTO_EXPOSURE_CANDIDATES)
    if not ctrl_ae:
        print("[ERROR] Auto exposure control not found.")
        return False
    ok = set_control(device, ctrl_ae, AE_AUTO)
    if ok:
        print(f"  [Exp] {ctrl_ae}={AE_AUTO} (auto mode)")
    return ok


# ============================================================
# Gain Control
# ============================================================

def set_gain(device, gain_value):
    """Set gain value. Note: gain may only take effect in manual exposure mode."""
    # Check if we're in manual exposure - warn user if not
    ctrl_ae = find_control_name(device, CTRL_AUTO_EXPOSURE_CANDIDATES)
    if ctrl_ae:
        ae_val = get_control(device, ctrl_ae)
        if ae_val and str(ae_val) != str(AE_MANUAL):
            print(f"  [Gain] WARN: {ctrl_ae}={ae_val} (not manual). "
                  f"Gain may not take visual effect.")

    ok = set_control(device, CTRL_GAIN, gain_value)
    if ok:
        actual = get_control(device, CTRL_GAIN)
        print(f"  [Gain] {CTRL_GAIN}={gain_value} (verified: {actual})")
    return ok


# ============================================================
# Status Display
# ============================================================

def show_status(device):
    """Show current camera status."""
    print("=" * 60)
    print(f"  Camera Status: {device}")
    print("=" * 60)

    # Identify the actual control names this kernel uses
    ctrl_trig = find_control_name(device, CTRL_TRIGGER_MODE_CANDIDATES)
    ctrl_ae = find_control_name(device, CTRL_AUTO_EXPOSURE_CANDIDATES)
    ctrl_exp = find_control_name(device, CTRL_EXPOSURE_VALUE_CANDIDATES)

    if ctrl_trig:
        v = get_control(device, ctrl_trig)
        mode = "TRIGGER" if v == "1" else "STREAM"
        print(f"  Mode:               {ctrl_trig} = {v} ({mode})")
    else:
        print(f"  Mode:               [trigger control not found]")

    if ctrl_ae:
        v = get_control(device, ctrl_ae)
        ae_mode = "MANUAL" if v == str(AE_MANUAL) else "AUTO" if v == str(AE_AUTO) else "?"
        print(f"  Exposure Mode:      {ctrl_ae} = {v} ({ae_mode})")

    if ctrl_exp:
        v = get_control(device, ctrl_exp)
        if v and v.isdigit():
            ms = int(v) / 10.0
            print(f"  Exposure Value:     {ctrl_exp} = {v} ({ms:.1f} ms)")
        else:
            print(f"  Exposure Value:     {ctrl_exp} = {v}")

    gain_v = get_control(device, CTRL_GAIN)
    print(f"  Gain:               {CTRL_GAIN} = {gain_v}")

    print()
    print("  Full control list:")
    print("-" * 60)
    print(list_controls(device))


# ============================================================
# Preview
# ============================================================

def preview(device, duration_sec=5):
    """Live preview to verify settings visually."""
    try:
        import cv2
    except ImportError:
        print("[Preview] cv2 not installed. pip3 install opencv-python")
        return

    # Convert /dev/videoN -> N
    m = re.search(r"/dev/video(\d+)", device)
    cam_idx = int(m.group(1)) if m else 0

    cap = cv2.VideoCapture(cam_idx, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"[Preview] Cannot open {device}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 800)
    cap.set(cv2.CAP_PROP_FPS, 120)

    print(f"[Preview] Showing {duration_sec}s. Press 'q' to quit early.")
    t0 = time.time()
    n = 0
    while time.time() - t0 < duration_sec:
        ret, frame = cap.read()
        if not ret:
            print("[Preview] Frame read timeout (in trigger mode? "
                  "send a pulse to FSIN to get a frame)")
            time.sleep(0.1)
            continue
        n += 1
        cv2.imshow("U20CAM-9281M Preview", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    elapsed = time.time() - t0
    fps = n / elapsed if elapsed > 0 else 0
    print(f"[Preview] {n} frames in {elapsed:.1f}s ({fps:.1f} fps measured)")
    cap.release()
    cv2.destroyAllWindows()


# ============================================================
# Main
# ============================================================

def main():
    p = argparse.ArgumentParser(
        description="Control U20CAM-9281M on Linux via v4l2-ctl",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("-d", "--device", default=None,
                   help="Camera device (default: auto-detect)")
    p.add_argument("--status", action="store_true",
                   help="Show current camera status and exit")
    p.add_argument("--mode", choices=["stream", "trigger"], default=None,
                   help="Switch operating mode")
    p.add_argument("--exposure", type=int, default=None,
                   help="Set exposure in UVC units (100us each)")
    p.add_argument("--exposure-ms", type=float, default=None,
                   help="Set exposure in milliseconds")
    p.add_argument("--auto-exposure", action="store_true",
                   help="Restore auto exposure")
    p.add_argument("--gain", type=int, default=None,
                   help="Set gain value")
    p.add_argument("--preview", action="store_true",
                   help="Show preview after applying settings")
    p.add_argument("--preview-duration", type=int, default=5,
                   help="Preview duration in seconds")
    args = p.parse_args()

    # Resolve device
    device = args.device or detect_camera()
    if not os.path.exists(device):
        print(f"[ERROR] Device not found: {device}")
        sys.exit(1)

    # Status mode - just print and exit
    if args.status:
        show_status(device)
        return

    # If no action specified, show status
    has_action = any([
        args.mode is not None,
        args.exposure is not None,
        args.exposure_ms is not None,
        args.auto_exposure,
        args.gain is not None,
        args.preview,
    ])
    if not has_action:
        show_status(device)
        return

    print("=" * 60)
    print(f"  Configuring {device}")
    print("=" * 60)

    # 1. Mode switch (do this first - trigger mode forces manual exposure)
    if args.mode == "stream":
        switch_to_stream_mode(device)
    elif args.mode == "trigger":
        switch_to_trigger_mode(device)

    # 2. Exposure
    if args.auto_exposure:
        set_auto_exposure(device)
    else:
        exposure_uvc = None
        if args.exposure is not None:
            exposure_uvc = args.exposure
        elif args.exposure_ms is not None:
            exposure_uvc = int(round(args.exposure_ms * 10))
            print(f"  [Convert] {args.exposure_ms} ms -> UVC value {exposure_uvc}")
        if exposure_uvc is not None:
            set_manual_exposure(device, exposure_uvc)

    # 3. Gain
    if args.gain is not None:
        set_gain(device, args.gain)

    # 4. Final status snapshot
    print()
    print("-" * 60)
    print("  Final state:")
    print("-" * 60)
    ctrl_trig = find_control_name(device, CTRL_TRIGGER_MODE_CANDIDATES)
    ctrl_ae = find_control_name(device, CTRL_AUTO_EXPOSURE_CANDIDATES)
    ctrl_exp = find_control_name(device, CTRL_EXPOSURE_VALUE_CANDIDATES)
    if ctrl_trig:
        print(f"  {ctrl_trig:30s} = {get_control(device, ctrl_trig)}")
    if ctrl_ae:
        print(f"  {ctrl_ae:30s} = {get_control(device, ctrl_ae)}")
    if ctrl_exp:
        print(f"  {ctrl_exp:30s} = {get_control(device, ctrl_exp)}")
    print(f"  {CTRL_GAIN:30s} = {get_control(device, CTRL_GAIN)}")

    # 5. Preview
    if args.preview:
        print()
        preview(device, args.preview_duration)


if __name__ == "__main__":
    main()
