# U20CAM-9281M Manual Exposure Control on macOS

## Overview

Setting manual exposure on UVC cameras via OpenCV on macOS is **unreliable** because
the AVFoundation backend has limited UVC control support. `cv2.CAP_PROP_EXPOSURE`
often does not take effect.

The reliable solution on macOS is to use **`uvc-util`**, a command-line tool that
talks to UVC controls directly. You set the exposure with `uvc-util` first, then
open the camera with OpenCV as usual.

## Setup

### 1. Install uvc-util

```bash
brew install uvc-util
```

If `brew tap` is not available, build from source:

```bash
git clone https://github.com/jtfrey/uvc-util.git
cd uvc-util
make
sudo cp uvc-util /usr/local/bin/
```

### 2. Install Python dependencies

```bash
pip3 install opencv-python numpy
```

### 3. Verify the camera is detected

```bash
uvc-util -I 0 -s
```

You should see a list of UVC controls including `exposure-time-abs`,
`auto-exposure-mode`, etc.

## Exposure Time Unit

UVC standard: **`exposure-time-abs` is in units of 100 microseconds (100us).**

| UVC Value | Exposure Time |
|-----------|---------------|
| 1         | 0.1 ms        |
| 10        | 1 ms          |
| 50        | 5 ms          |
| 83        | 8.3 ms (~120fps limit) |
| 100       | 10 ms         |
| 200       | 20 ms         |
| 333       | 33.3 ms (~30fps limit) |

For 120fps capture, the maximum exposure is ~8.3 ms (UVC value 83).

## Usage

### Quick Start: Set 5ms exposure

```bash
# Step 1: switch to manual exposure mode
uvc-util -I 0 -s auto-exposure-mode=1

# Step 2: set exposure to 5 ms
uvc-util -I 0 -s exposure-time-abs=50

# Step 3: verify
uvc-util -I 0 -g exposure-time-abs

# Step 4: run your OpenCV Python code as usual
python3 your_capture_script.py
```

### Using the Helper Script

The `u20cam_exposure_macos.py` script wraps these commands:

```bash
# List camera controls
python3 u20cam_exposure_macos.py --list

# Set 20ms exposure
python3 u20cam_exposure_macos.py --exposure-ms 20

# Set 5ms exposure with live preview
python3 u20cam_exposure_macos.py --exposure-ms 5 --preview

# Restore auto exposure
python3 u20cam_exposure_macos.py --auto
```

### Minimal Python Example

See `minimal_120fps_with_exposure.py` for a complete example that:

1. Sets manual exposure via `uvc-util`
2. Opens the camera via OpenCV
3. Captures 120fps video to file

```python
import cv2
import subprocess

CAMERA_INDEX = 0
EXPOSURE_MS = 5.0

# Set manual exposure BEFORE opening with OpenCV
subprocess.run(["uvc-util", "-I", str(CAMERA_INDEX),
                "-s", "auto-exposure-mode=1"], check=True)
subprocess.run(["uvc-util", "-I", str(CAMERA_INDEX),
                "-s", f"exposure-time-abs={int(EXPOSURE_MS * 10)}"], check=True)

# Then open camera with OpenCV as usual
cap = cv2.VideoCapture(CAMERA_INDEX)
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

## UVC Control Reference

| uvc-util name           | Meaning                          | Values |
|-------------------------|----------------------------------|--------|
| `auto-exposure-mode`    | Exposure mode                    | 1=manual, 2=auto, 4=shutter priority, 8=aperture priority |
| `exposure-time-abs`     | Exposure time (100us units)      | 1 to ~10000 |
| `gain`                  | Sensor gain                      | 0-64 (model-dependent) |
| `brightness`            | Brightness                       | model-dependent |

## Troubleshooting

### `uvc-util` says "no devices"

Make sure no other application is using the camera (close FaceTime, Photo Booth, etc.).

### Exposure value is set but image brightness does not change

Check that `auto-exposure-mode=1` succeeded. If the camera is still in auto mode,
it will override your manual exposure value.

```bash
uvc-util -I 0 -g auto-exposure-mode
```

Should return `1`.

### Frame rate drops after setting long exposure

This is expected. Frame rate is limited by `1 / exposure_time`:
- 8.3 ms exposure → max ~120 fps
- 16.6 ms exposure → max ~60 fps
- 33.3 ms exposure → max ~30 fps

If you need both long exposure AND high frame rate, that physically cannot work.

### OpenCV `cv2.CAP_PROP_EXPOSURE` does not work

Confirmed limitation of OpenCV's AVFoundation backend on macOS. Use `uvc-util` instead.

## Why This Works

UVC (USB Video Class) cameras expose standardized controls over USB. On Linux
these are accessed via `v4l2-ctl`. On macOS, `uvc-util` provides equivalent
functionality by talking to IOKit directly.

OpenCV on macOS uses AVFoundation, which abstracts the camera into a high-level
interface and exposes only a small subset of UVC controls. Setting exposure
outside of OpenCV (via `uvc-util`) bypasses this limitation - the setting is
stored in the camera's firmware, and OpenCV simply reads frames from a camera
that already has the correct exposure applied.
