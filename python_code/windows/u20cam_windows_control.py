#!/usr/bin/env python3
"""
U20CAM-9281M Universal Control Script for Windows
==================================================

Control U20CAM-9281M on Windows via OpenCV (DirectShow) and optional
DirectShow COM interface.

Features:
  - Switch between Stream Mode and Trigger Mode (best-effort)
  - Set manual exposure value (in milliseconds, auto-converted to log2)
  - Set gain value
  - Restore auto exposure
  - Live preview to verify settings

Two control paths (tried in order):
  1. OpenCV with CAP_DSHOW backend  (works for most controls)
  2. DirectShow COM via comtypes    (fallback for trigger mode and
                                     when OpenCV path fails)

Important Differences from Linux/macOS:
  - DirectShow uses log2 seconds for exposure, NOT UVC 100us units
       Linux:  exposure_time_absolute = 50      (= 5 ms in 100us units)
       Windows: CAP_PROP_EXPOSURE     = -7.64   (= log2(0.005))
  - The script converts milliseconds <-> log2 internally so you always
    pass --exposure-ms for consistency across platforms.
  - MSMF (default) backend has poor UVC control support. The script
    explicitly uses CAP_DSHOW.

Trigger Mode Limitation:
  Trigger mode requires setting the UVC AutoFocus control to enable.
  DirectShow exposes AutoFocus as a boolean via IAMCameraControl, which
  some firmwares accept as the trigger toggle and some do not. If the
  OpenCV/DirectShow path fails to switch trigger mode, you may need to
  use the InnoMaker AMCap utility on Windows for trigger mode setup.

Requirements:
  pip install opencv-python numpy
  pip install comtypes        (optional, for fallback path)

Usage:
  # Show camera status
  python u20cam_windows_control.py --status

  # List available camera indices
  python u20cam_windows_control.py --list

  # Stream mode + manual exposure 5ms + gain 32
  python u20cam_windows_control.py --mode stream --exposure-ms 5 --gain 32

  # Restore auto exposure
  python u20cam_windows_control.py --auto-exposure

  # Switch to trigger mode (best-effort)
  python u20cam_windows_control.py --mode trigger

  # Apply settings + live preview
  python u20cam_windows_control.py --mode stream --exposure-ms 5 --gain 32 --preview

  # Specify camera index
  python u20cam_windows_control.py -c 1 --status
"""

import argparse
import math
import sys
import time


# ============================================================
# Exposure Unit Conversion (log2 seconds <-> milliseconds)
# ============================================================
#
# DirectShow exposure value semantics:
#   value = log2(exposure_in_seconds)
#
# Examples:
#   -1   = 0.500 s    = 500   ms
#   -5   = 0.0312 s   = 31.25 ms
#   -6   = 0.0156 s   = 15.6  ms
#   -7   = 0.0078 s   = 7.8   ms (~120fps max)
#   -8   = 0.00390 s  = 3.9   ms
#   -9   = 0.00195 s  = 1.95  ms
#  -10   = 0.00098 s  = 0.98  ms
#  -11   = 0.00049 s  = 0.49  ms
#  -12   = 0.00024 s  = 0.24  ms
#  -13   = 0.00012 s  = 0.12  ms

def ms_to_log2(exposure_ms):
    """Convert milliseconds to DirectShow log2-seconds exposure value."""
    seconds = exposure_ms / 1000.0
    if seconds <= 0:
        return -13  # smallest practical
    return math.log2(seconds)


def log2_to_ms(log2_value):
    """Convert DirectShow log2-seconds exposure value back to milliseconds."""
    seconds = 2 ** log2_value
    return seconds * 1000.0


# ============================================================
# OpenCV DirectShow Path
# ============================================================

def opencv_open(camera_index):
    """Open camera with DirectShow backend (required on Windows for UVC controls)."""
    try:
        import cv2
    except ImportError:
        print("[ERROR] OpenCV not installed. pip install opencv-python")
        sys.exit(1)

    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open camera {camera_index} with DirectShow backend")
        return None
    return cap


def opencv_set_manual_exposure(cap, exposure_ms):
    """Set manual exposure via OpenCV DirectShow."""
    import cv2

    # Step 1: switch to manual exposure mode (DirectShow: 0.25 = manual)
    ok_mode = cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)

    # Step 2: convert ms to log2 and apply
    log2_value = ms_to_log2(exposure_ms)
    # Round to nearest integer because DirectShow camera filters typically
    # only accept integer log2 steps
    rounded_log2 = round(log2_value)
    actual_ms = log2_to_ms(rounded_log2)

    print(f"  [Exp] Target: {exposure_ms} ms")
    print(f"  [Exp] log2 value: {log2_value:.2f} -> rounded {rounded_log2} "
          f"(actual {actual_ms:.2f} ms)")

    ok_exp = cap.set(cv2.CAP_PROP_EXPOSURE, rounded_log2)

    # Step 3: read back
    actual_log2 = cap.get(cv2.CAP_PROP_EXPOSURE)
    actual_back_ms = log2_to_ms(actual_log2)
    print(f"  [Exp] Verify: CAP_PROP_EXPOSURE = {actual_log2} "
          f"({actual_back_ms:.2f} ms)")

    return ok_mode and ok_exp


def opencv_set_auto_exposure(cap):
    """Restore auto exposure (DirectShow: 0.75 = auto)."""
    import cv2
    ok = cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
    print(f"  [Exp] Auto exposure {'OK' if ok else 'FAILED'}")
    return ok


def opencv_set_gain(cap, gain_value):
    """Set gain via OpenCV DirectShow."""
    import cv2
    # Check current exposure mode
    ae = cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)
    if abs(ae - 0.25) > 0.01:
        print(f"  [Gain] WARN: AUTO_EXPOSURE={ae}. Gain may not take effect "
              f"(switch to manual exposure first).")

    ok = cap.set(cv2.CAP_PROP_GAIN, gain_value)
    actual = cap.get(cv2.CAP_PROP_GAIN)
    print(f"  [Gain] Set {gain_value}, verify: {actual} ({'OK' if ok else 'FAILED'})")
    return ok


def opencv_set_trigger_mode(cap, enable):
    """
    Best-effort trigger mode toggle.

    DirectShow does not have a standard "trigger mode" property.
    Some firmwares map the AutoFocus control (CAP_PROP_AUTOFOCUS) to
    trigger toggle. This is the same convention as on Linux where
    focus_automatic_continuous is repurposed for trigger.
    """
    import cv2
    value = 1 if enable else 0
    ok = cap.set(cv2.CAP_PROP_AUTOFOCUS, value)
    actual = cap.get(cv2.CAP_PROP_AUTOFOCUS)
    mode_str = "TRIGGER" if enable else "STREAM"
    print(f"  [Mode] CAP_PROP_AUTOFOCUS={value} (-> {mode_str}), "
          f"verify: {actual} ({'OK' if ok else 'FAILED'})")
    if not ok or actual != value:
        print(f"  [Mode] WARN: trigger mode toggle may not have taken effect.")
        print(f"         Consider using InnoMaker AMCap utility instead.")
    return ok


# ============================================================
# Status Display
# ============================================================

def show_status(camera_index):
    """Show current camera status via OpenCV."""
    import cv2

    print("=" * 60)
    print(f"  Camera Status: index {camera_index} (DirectShow)")
    print("=" * 60)

    cap = opencv_open(camera_index)
    if not cap:
        return

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    ae = cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)
    exp = cap.get(cv2.CAP_PROP_EXPOSURE)
    gain = cap.get(cv2.CAP_PROP_GAIN)
    af = cap.get(cv2.CAP_PROP_AUTOFOCUS)

    ae_mode = "MANUAL" if abs(ae - 0.25) < 0.01 else \
              "AUTO" if abs(ae - 0.75) < 0.01 else f"? ({ae})"

    trig_mode = "TRIGGER" if af == 1 else "STREAM" if af == 0 else f"? ({af})"

    exp_ms = log2_to_ms(exp) if exp != 0 else 0

    print(f"  Resolution:        {width} x {height}")
    print(f"  Frame Rate:        {fps:.1f} fps")
    print(f"  Mode (AutoFocus):  {af} ({trig_mode})")
    print(f"  Exposure Mode:     {ae} ({ae_mode})")
    print(f"  Exposure Value:    {exp} (log2 sec) = {exp_ms:.2f} ms")
    print(f"  Gain:              {gain}")

    cap.release()


def list_cameras(max_index=8):
    """Probe camera indices 0..max_index-1 to find available cameras."""
    import cv2

    print("=" * 60)
    print("  Probing camera indices 0 to {}...".format(max_index - 1))
    print("=" * 60)

    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"  [{i}] OPEN  - default {w}x{h}")
            found.append(i)
            cap.release()
        else:
            # Don't print failed ones to keep output clean
            pass

    if not found:
        print("  No cameras found.")
    else:
        print(f"\n  Found cameras at indices: {found}")
    return found


# ============================================================
# Preview
# ============================================================

def preview(camera_index, duration_sec=5):
    """Live preview window."""
    import cv2

    cap = opencv_open(camera_index)
    if not cap:
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 800)
    cap.set(cv2.CAP_PROP_FPS, 120)

    print(f"[Preview] Showing for {duration_sec}s. Press 'q' to quit early.")
    t0 = time.time()
    n = 0
    while time.time() - t0 < duration_sec:
        ret, frame = cap.read()
        if not ret:
            print("[Preview] Frame read failed. "
                  "(In trigger mode? Camera waits for FSIN pulse.)")
            time.sleep(0.1)
            continue
        n += 1
        cv2.imshow("U20CAM-9281M Preview (Windows)", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
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
        description="Control U20CAM-9281M on Windows via OpenCV/DirectShow",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("-c", "--camera", type=int, default=0,
                   help="Camera index (default: 0)")
    p.add_argument("--list", action="store_true",
                   help="Probe and list available camera indices")
    p.add_argument("--status", action="store_true",
                   help="Show current camera status")
    p.add_argument("--mode", choices=["stream", "trigger"], default=None,
                   help="Switch operating mode")
    p.add_argument("--exposure-ms", type=float, default=None,
                   help="Manual exposure in milliseconds")
    p.add_argument("--auto-exposure", action="store_true",
                   help="Restore auto exposure")
    p.add_argument("--gain", type=float, default=None,
                   help="Set gain value")
    p.add_argument("--preview", action="store_true",
                   help="Show live preview after applying settings")
    p.add_argument("--preview-duration", type=int, default=5,
                   help="Preview duration in seconds (default: 5)")
    args = p.parse_args()

    # ---- List mode ----
    if args.list:
        list_cameras()
        return

    # ---- Status mode ----
    if args.status:
        show_status(args.camera)
        return

    # ---- If no action, show status ----
    has_action = any([
        args.mode is not None,
        args.exposure_ms is not None,
        args.auto_exposure,
        args.gain is not None,
        args.preview,
    ])
    if not has_action:
        show_status(args.camera)
        return

    # ---- Apply settings ----
    print("=" * 60)
    print(f"  Configuring camera {args.camera} (DirectShow)")
    print("=" * 60)

    cap = opencv_open(args.camera)
    if not cap:
        sys.exit(1)

    try:
        # 1. Mode switch (do this first)
        if args.mode == "stream":
            opencv_set_trigger_mode(cap, enable=False)
        elif args.mode == "trigger":
            # Trigger mode requires manual exposure
            opencv_set_manual_exposure(cap, args.exposure_ms or 5.0)
            opencv_set_trigger_mode(cap, enable=True)

        # 2. Exposure
        if args.auto_exposure:
            opencv_set_auto_exposure(cap)
        elif args.exposure_ms is not None and args.mode != "trigger":
            opencv_set_manual_exposure(cap, args.exposure_ms)

        # 3. Gain
        if args.gain is not None:
            opencv_set_gain(cap, args.gain)

        # 4. Final state
        print()
        print("-" * 60)
        print("  Final state:")
        print("-" * 60)
        import cv2
        af = cap.get(cv2.CAP_PROP_AUTOFOCUS)
        ae = cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)
        exp = cap.get(cv2.CAP_PROP_EXPOSURE)
        exp_ms = log2_to_ms(exp) if exp != 0 else 0
        gain = cap.get(cv2.CAP_PROP_GAIN)
        print(f"  AUTOFOCUS (mode):   {af}")
        print(f"  AUTO_EXPOSURE:      {ae}")
        print(f"  EXPOSURE (log2 s):  {exp} ({exp_ms:.2f} ms)")
        print(f"  GAIN:               {gain}")
    finally:
        cap.release()

    # 5. Preview (re-open separately so above settings persist in the camera)
    if args.preview:
        print()
        preview(args.camera, args.preview_duration)


if __name__ == "__main__":
    main()
