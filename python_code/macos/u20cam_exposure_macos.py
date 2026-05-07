#!/usr/bin/env python3
"""
U20CAM-9281M Manual Exposure Control on macOS
===============================================

Set manual exposure and exposure time on U20CAM-9281M under OpenCV on macOS.

Background:
  macOS + OpenCV (AVFoundation backend) has poor UVC control support.
  CAP_PROP_EXPOSURE often fails to take effect. This script tries three
  methods in order of reliability:

    Method 1: uvc-util  (most reliable on macOS)
    Method 2: OpenCV cv2.CAP_PROP_EXPOSURE  (simple, may not work)
    Method 3: PyUSB + UVC protocol  (ultimate fallback)

Exposure Time Unit:
  UVC standard: exposure_absolute is in units of 100 microseconds (100us).
    value 1   = 0.1 ms
    value 10  = 1 ms
    value 100 = 10 ms
    value 200 = 20 ms
    value 333 = 33.3 ms (~30fps limit)

Recommended Setup on macOS:
  1. Install Homebrew (if not yet):
     /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  2. Install uvc-util:
     brew install uvc-util
     # If brew tap not available, build from source:
     # git clone https://github.com/jtfrey/uvc-util.git
     # cd uvc-util && make && sudo cp uvc-util /usr/local/bin/

  3. Install Python deps:
     pip3 install opencv-python numpy

Usage:
  # Show current camera controls
  python3 u20cam_exposure_macos.py --list

  # Set manual exposure mode + exposure value (UVC units, 100us)
  python3 u20cam_exposure_macos.py --exposure 200          # 20ms

  # Set exposure in milliseconds (auto-converts to UVC units)
  python3 u20cam_exposure_macos.py --exposure-ms 20        # 20ms

  # Set exposure + capture preview to verify
  python3 u20cam_exposure_macos.py --exposure-ms 10 --preview

  # Restore auto exposure
  python3 u20cam_exposure_macos.py --auto

  # Specify camera index (default: 0)
  python3 u20cam_exposure_macos.py --exposure-ms 20 --camera 0
"""

import argparse
import subprocess
import sys
import shutil
import time


# ============================================================
# Method 1: uvc-util (recommended on macOS)
# ============================================================

def has_uvc_util():
    """Check if uvc-util is available."""
    return shutil.which("uvc-util") is not None


def uvc_util_list_devices():
    """List UVC devices visible to uvc-util."""
    try:
        out = subprocess.run(
            ["uvc-util", "-I"],
            capture_output=True, text=True, timeout=5
        )
        return out.stdout
    except Exception as e:
        return f"[ERROR] {e}"


def uvc_util_list_controls(index=0):
    """List all UVC controls for a device."""
    try:
        out = subprocess.run(
            ["uvc-util", "-I", str(index), "-s"],
            capture_output=True, text=True, timeout=5
        )
        return out.stdout
    except Exception as e:
        return f"[ERROR] {e}"


def uvc_util_set_manual_exposure(index=0):
    """Set exposure mode to manual (UVC value 1)."""
    # UVC auto-exposure-mode: 1 = manual, 2 = auto, 4 = shutter priority, 8 = aperture priority
    try:
        result = subprocess.run(
            ["uvc-util", "-I", str(index),
             "-s", "auto-exposure-mode=1"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            print("  [uvc-util] Set auto-exposure-mode = 1 (manual)")
            return True
        print(f"  [uvc-util] FAILED: {result.stderr.strip()}")
        return False
    except Exception as e:
        print(f"  [uvc-util] ERROR: {e}")
        return False


def uvc_util_set_auto_exposure(index=0):
    """Restore auto exposure (UVC value 2 or 8)."""
    try:
        # try aperture priority first (most cameras default to this)
        result = subprocess.run(
            ["uvc-util", "-I", str(index),
             "-s", "auto-exposure-mode=8"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            print("  [uvc-util] Set auto-exposure-mode = 8 (aperture priority)")
            return True
        # fallback to "auto"
        result = subprocess.run(
            ["uvc-util", "-I", str(index),
             "-s", "auto-exposure-mode=2"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception as e:
        print(f"  [uvc-util] ERROR: {e}")
        return False


def uvc_util_set_exposure_time(index=0, value_uvc=200):
    """Set exposure time absolute (UVC units, 100us)."""
    try:
        result = subprocess.run(
            ["uvc-util", "-I", str(index),
             "-s", f"exposure-time-abs={value_uvc}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            ms = value_uvc / 10.0
            print(f"  [uvc-util] Set exposure-time-abs = {value_uvc} ({ms:.1f} ms)")
            return True
        print(f"  [uvc-util] FAILED: {result.stderr.strip()}")
        return False
    except Exception as e:
        print(f"  [uvc-util] ERROR: {e}")
        return False


def uvc_util_get_exposure(index=0):
    """Read current exposure value back."""
    try:
        result = subprocess.run(
            ["uvc-util", "-I", str(index),
             "-g", "exposure-time-abs"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception as e:
        return f"[ERROR] {e}"


# ============================================================
# Method 2: OpenCV cv2.CAP_PROP_EXPOSURE (fallback)
# ============================================================

def opencv_set_exposure(camera_index, exposure_value):
    """
    Try to set exposure via OpenCV directly.
    On macOS this often does NOT work for UVC cameras,
    but worth trying as a fallback.
    """
    try:
        import cv2
    except ImportError:
        print("  [OpenCV] cv2 not installed: pip3 install opencv-python")
        return False

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"  [OpenCV] Cannot open camera {camera_index}")
        return False

    # On macOS, AVFoundation backend:
    #   CAP_PROP_AUTO_EXPOSURE: 0.25 = manual, 0.75 = auto (Linux convention)
    #   on macOS the values may differ - try both 1/3 and 0.25/0.75
    print("  [OpenCV] Attempting to set manual exposure mode...")
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)        # Linux: manual
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)     # alt: manual

    print(f"  [OpenCV] Setting CAP_PROP_EXPOSURE = {exposure_value}")
    ok = cap.set(cv2.CAP_PROP_EXPOSURE, exposure_value)
    actual = cap.get(cv2.CAP_PROP_EXPOSURE)
    print(f"  [OpenCV] set() returned {ok}, get() returned {actual}")

    cap.release()
    return ok


# ============================================================
# Preview (uses OpenCV, works regardless of how exposure was set)
# ============================================================

def preview(camera_index=0, duration_sec=5):
    """Open preview window for visual confirmation."""
    try:
        import cv2
    except ImportError:
        print("[Preview] cv2 not installed.")
        return

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"[Preview] Cannot open camera {camera_index}")
        return

    # set 120fps mode if supported
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 800)
    cap.set(cv2.CAP_PROP_FPS, 120)

    print(f"[Preview] Showing camera for {duration_sec}s. Press 'q' to quit.")
    t0 = time.time()
    n = 0
    while time.time() - t0 < duration_sec:
        ret, frame = cap.read()
        if not ret:
            break
        n += 1
        cv2.imshow("U20CAM-9281M Preview", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    elapsed = time.time() - t0
    fps = n / elapsed if elapsed > 0 else 0
    print(f"[Preview] Captured {n} frames in {elapsed:.1f}s ({fps:.1f} fps)")
    cap.release()
    cv2.destroyAllWindows()


# ============================================================
# Main
# ============================================================

def main():
    p = argparse.ArgumentParser(
        description="Set manual exposure on U20CAM-9281M (macOS)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--camera", "-c", type=int, default=0,
                   help="Camera index (default: 0)")
    p.add_argument("--list", action="store_true",
                   help="List camera controls and exit")
    p.add_argument("--exposure", type=int, default=None,
                   help="Exposure value in UVC units (100us each)")
    p.add_argument("--exposure-ms", type=float, default=None,
                   help="Exposure time in milliseconds")
    p.add_argument("--auto", action="store_true",
                   help="Restore auto exposure")
    p.add_argument("--preview", action="store_true",
                   help="Show preview after setting exposure")
    p.add_argument("--preview-duration", type=int, default=5,
                   help="Preview duration in seconds (default: 5)")
    args = p.parse_args()

    # ---- List mode ----
    if args.list:
        print("=" * 60)
        print("  U20CAM-9281M Camera Information")
        print("=" * 60)
        if has_uvc_util():
            print("\n[uvc-util] Available devices:")
            print(uvc_util_list_devices())
            print(f"\n[uvc-util] Controls for device {args.camera}:")
            print(uvc_util_list_controls(args.camera))
        else:
            print("\n[WARN] uvc-util not found. Install with: brew install uvc-util")
            print("       Or build from: https://github.com/jtfrey/uvc-util")
        return

    # ---- Auto exposure mode ----
    if args.auto:
        print("=" * 60)
        print("  Restoring Auto Exposure")
        print("=" * 60)
        if has_uvc_util():
            uvc_util_set_auto_exposure(args.camera)
        else:
            print("[WARN] uvc-util not found - using OpenCV fallback")
            try:
                import cv2
                cap = cv2.VideoCapture(args.camera)
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3)    # Linux: aperture priority/auto
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75) # alt convention
                cap.release()
            except ImportError:
                print("[ERROR] cv2 not installed.")
        if args.preview:
            preview(args.camera, args.preview_duration)
        return

    # ---- Determine exposure value ----
    exposure_uvc = None
    if args.exposure is not None:
        exposure_uvc = args.exposure
    elif args.exposure_ms is not None:
        exposure_uvc = int(round(args.exposure_ms * 10))
        print(f"[INFO] Converted {args.exposure_ms}ms to UVC value {exposure_uvc}")
    else:
        p.print_help()
        print("\n[ERROR] Need --exposure, --exposure-ms, --auto, or --list")
        sys.exit(1)

    # ---- Set manual exposure ----
    print("=" * 60)
    print(f"  Setting Manual Exposure: {exposure_uvc} ({exposure_uvc/10.0:.1f} ms)")
    print("=" * 60)

    success = False

    # Method 1: uvc-util
    if has_uvc_util():
        print("\n[Method 1] Using uvc-util...")
        ok1 = uvc_util_set_manual_exposure(args.camera)
        ok2 = uvc_util_set_exposure_time(args.camera, exposure_uvc)
        if ok1 and ok2:
            success = True
            actual = uvc_util_get_exposure(args.camera)
            print(f"  [uvc-util] Verified: {actual}")
    else:
        print("\n[Method 1] uvc-util not found - skipping")
        print("           To install: brew install uvc-util")

    # Method 2: OpenCV fallback (only if Method 1 failed)
    if not success:
        print("\n[Method 2] Trying OpenCV fallback...")
        success = opencv_set_exposure(args.camera, exposure_uvc)
        if success:
            print("  [OpenCV] set() reported success - but may not actually take effect on macOS")
            print("  [OpenCV] Use --preview to visually verify")

    if not success:
        print("\n[FAIL] Could not set exposure via any method.")
        print("       Please install uvc-util:  brew install uvc-util")
        sys.exit(1)

    # ---- Preview if requested ----
    if args.preview:
        print()
        preview(args.camera, args.preview_duration)


if __name__ == "__main__":
    main()
