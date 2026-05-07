# U20CAM-9281M Windows Control Script

Python3 script for controlling U20CAM-9281M on Windows via OpenCV
(DirectShow backend).

## Features

- Switch between **Stream Mode** and **Trigger Mode** (best-effort)
- Set manual exposure value (in milliseconds, auto-converted internally)
- Set gain value
- Restore auto exposure
- Live preview to verify settings
- List available camera indices

## Requirements

```cmd
pip install opencv-python numpy
```

No additional drivers needed. The U20CAM-9281M is a UVC-class device
and uses the standard Windows USB Video Class driver.

## Critical Windows-Specific Points

### 1. Use DirectShow Backend, NOT MSMF

Windows OpenCV defaults to the MSMF (Media Foundation) backend, which has
**very limited UVC control support**. You must explicitly request the
DirectShow backend:

```python
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)   # CORRECT
cap = cv2.VideoCapture(0)                  # WRONG (uses MSMF, exposure won't work)
```

### 2. Exposure Value Uses log2(seconds), NOT UVC 100us Units

Unlike Linux (`v4l2-ctl`) or macOS (`uvc-util`), DirectShow uses a
logarithmic exposure scale:

```
   exposure_value = log2(exposure_in_seconds)
```

| log2 Value | Exposure | Max FPS |
|-----------|----------|---------|
| -5        | 31.25 ms | ~30     |
| -6        | 15.6 ms  | ~60     |
| -7        | 7.8 ms   | ~120    |
| -8        | 3.9 ms   | ~120    |
| -9        | 1.95 ms  | ~120    |
| -10       | 0.98 ms  | -       |
| -11       | 0.49 ms  | -       |
| -12       | 0.24 ms  | -       |
| -13       | 0.12 ms  | -       |

The script handles this conversion internally - you always pass exposure
in milliseconds via `--exposure-ms`.

### 3. AUTO_EXPOSURE Values

DirectShow uses floating-point values for the exposure mode property:

| Value | Meaning |
|-------|---------|
| 0.25  | Manual exposure |
| 0.75  | Auto exposure |

The script handles this automatically.

## Quick Start

### List available cameras
```cmd
python u20cam_windows_control.py --list
```

### Show camera status
```cmd
python u20cam_windows_control.py --status
```

Example output:
```
============================================================
  Camera Status: index 0 (DirectShow)
============================================================
  Resolution:        1280 x 800
  Frame Rate:        120.0 fps
  Mode (AutoFocus):  0.0 (STREAM)
  Exposure Mode:     0.25 (MANUAL)
  Exposure Value:    -7.0 (log2 sec) = 7.81 ms
  Gain:              32.0
```

### Stream mode + manual exposure 5ms + gain 32
```cmd
python u20cam_windows_control.py --mode stream --exposure-ms 5 --gain 32
```

### Stream mode + auto exposure
```cmd
python u20cam_windows_control.py --mode stream --auto-exposure
```

### Apply settings + live preview
```cmd
python u20cam_windows_control.py --mode stream --exposure-ms 5 --gain 32 --preview
```

### Just change exposure (keep current mode)
```cmd
python u20cam_windows_control.py --exposure-ms 10
```

### Just change gain
```cmd
python u20cam_windows_control.py --gain 16
```

### Specify camera index
```cmd
python u20cam_windows_control.py -c 1 --status
```

## Command-Line Arguments

| Argument | Description |
|----------|-------------|
| `-c`, `--camera` | Camera index (default: 0) |
| `--list` | Probe and list available camera indices |
| `--status` | Show current camera status |
| `--mode {stream,trigger}` | Switch operating mode |
| `--exposure-ms N` | Set exposure in milliseconds |
| `--auto-exposure` | Restore auto exposure |
| `--gain N` | Set gain value |
| `--preview` | Show live preview after applying settings |
| `--preview-duration N` | Preview duration in seconds (default: 5) |

## Trigger Mode on Windows: Important Limitation

DirectShow does NOT have a standard "trigger mode" property. The script
attempts to enable trigger mode via `CAP_PROP_AUTOFOCUS`, which some
firmwares map to the trigger toggle (similar to how Linux uses
`focus_automatic_continuous`).

**This may or may not work depending on firmware version.**

If the script reports "trigger mode toggle may not have taken effect",
use one of these alternatives:

### Option A: InnoMaker AMCap Utility

Download AMCap from InnoMaker. It is a Windows GUI tool that talks to
the camera via DirectShow and can reliably toggle trigger mode through
its property pages.

1. Open AMCap
2. Devices -> select U20CAM-9281M
3. Options -> Video Capture Filter -> Camera Control tab
4. Toggle "Focus" to enable trigger mode

After toggling in AMCap, close AMCap and run your Python capture code.
The trigger mode setting persists in the camera until you toggle it off
or unplug the device.

### Option B: Boot into Linux

If you need scriptable trigger mode control, the Linux script
(`u20cam_linux_control.py`) is more reliable for this use case because
v4l2-ctl directly supports the `focus_automatic_continuous` property.

## Minimal Python Example

See `minimal_120fps_windows.py` for a complete working example:

```python
import cv2
import math

CAMERA_INDEX = 0
EXPOSURE_MS = 5.0

# Open with DirectShow backend (REQUIRED on Windows)
cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)

# Manual exposure mode (DirectShow: 0.25 = manual)
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)

# Convert ms to log2 seconds and set
log2_value = round(math.log2(EXPOSURE_MS / 1000.0))
cap.set(cv2.CAP_PROP_EXPOSURE, log2_value)

# Set capture format
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 800)
cap.set(cv2.CAP_PROP_FPS, 120)

while True:
    ret, frame = cap.read()
    if not ret:
        break
    cv2.imshow("preview", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
```

## Troubleshooting

### Exposure value is set but image brightness does not change

Most common cause: you forgot to set `CAP_PROP_AUTO_EXPOSURE = 0.25`
(manual mode) before setting the exposure value. The auto exposure
algorithm will override your manual value.

Fix: always set both, in this order:
```python
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)   # FIRST
cap.set(cv2.CAP_PROP_EXPOSURE, log2_value)  # THEN
```

### Camera opens but cap.set(EXPOSURE) returns False

You are using the MSMF backend. Switch to DirectShow:
```python
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
```

### "Cannot open camera 0"

- Check Device Manager -> Imaging devices -> verify the camera shows up
- Close any other application using the camera (Skype, Teams, Zoom, AMCap)
- Try a different USB port
- Try a different camera index (`--list` to probe all)

### Frame rate drops below 120fps

Frame rate is physically limited by exposure time:
- 7.8 ms exposure -> max ~120 fps
- 15.6 ms exposure -> max ~60 fps
- 31.25 ms exposure -> max ~30 fps

If you want 120fps, use exposure of 7.8ms or shorter.

### "ImportError: No module named cv2"

```cmd
pip install opencv-python
```

### Gain change has no visible effect

Cause: camera is in auto exposure mode. Switch to manual exposure first:
```cmd
python u20cam_windows_control.py --mode stream --exposure-ms 5 --gain 32
```

### Preview window shows no frames in trigger mode

Expected behavior. Trigger mode requires an external pulse on the FSIN
pin. Switch back to stream mode:
```cmd
python u20cam_windows_control.py --mode stream --preview
```

## Comparison: Linux vs macOS vs Windows

| Aspect | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Tool | `v4l2-ctl` | `uvc-util` | OpenCV CAP_DSHOW |
| Exposure unit | 100us (UVC standard) | 100us (UVC standard) | log2(seconds) |
| OpenCV backend needed | V4L2 (default) | AVFoundation (default) | **CAP_DSHOW (must specify)** |
| Manual exp value | `auto_exposure=1` | `auto-exposure-mode=1` | `CAP_PROP_AUTO_EXPOSURE=0.25` |
| Auto exp value | `auto_exposure=3` | `auto-exposure-mode=8` | `CAP_PROP_AUTO_EXPOSURE=0.75` |
| Trigger mode | `focus_automatic_continuous=1` | `auto-focus=1` (firmware-dependent) | `CAP_PROP_AUTOFOCUS=1` (firmware-dependent) |
| Trigger mode reliability | High | Medium | Low (use AMCap if needed) |

## OpenCV DirectShow Property Reference

| Property | DirectShow Meaning |
|----------|-------------------|
| `CAP_PROP_EXPOSURE` | Exposure (log2 seconds) |
| `CAP_PROP_AUTO_EXPOSURE` | Exposure mode (0.25=manual, 0.75=auto) |
| `CAP_PROP_GAIN` | Sensor gain |
| `CAP_PROP_AUTOFOCUS` | Autofocus / repurposed for trigger mode |
| `CAP_PROP_BRIGHTNESS` | Brightness offset |
| `CAP_PROP_CONTRAST` | Contrast |
| `CAP_PROP_SATURATION` | Saturation |
| `CAP_PROP_FRAME_WIDTH` | Frame width |
| `CAP_PROP_FRAME_HEIGHT` | Frame height |
| `CAP_PROP_FPS` | Frame rate |
