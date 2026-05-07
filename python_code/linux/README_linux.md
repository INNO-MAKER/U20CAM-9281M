# U20CAM-9281M Linux Control Script

A universal Python3 script for controlling U20CAM-9281M on Linux via `v4l2-ctl`.

## Features

- Switch between **Stream Mode** (free-running) and **Trigger Mode** (FSIN-driven)
- Set manual exposure value in stream mode (UVC units or milliseconds)
- Set gain value in stream mode
- Restore auto exposure
- Live preview to verify settings
- Compatible with both old and new Linux kernel control names
- Auto-detects camera device

## Requirements

```bash
sudo apt install v4l-utils python3-opencv
pip3 install opencv-python numpy
```

## Quick Start

### Show current camera status
```bash
python3 u20cam_linux_control.py --status
```

Example output:
```
============================================================
  Camera Status: /dev/video0
============================================================
  Mode:               focus_automatic_continuous = 0 (STREAM)
  Exposure Mode:      auto_exposure = 1 (MANUAL)
  Exposure Value:     exposure_time_absolute = 50 (5.0 ms)
  Gain:               gain = 32
```

### Stream mode with manual exposure 5ms + gain 32
```bash
python3 u20cam_linux_control.py --mode stream --exposure-ms 5 --gain 32
```

### Stream mode with auto exposure
```bash
python3 u20cam_linux_control.py --mode stream --auto-exposure
```

### Switch to trigger mode (waits for external FSIN pulse)
```bash
python3 u20cam_linux_control.py --mode trigger
```

### Apply settings + live preview to verify
```bash
python3 u20cam_linux_control.py --mode stream --exposure-ms 5 --gain 32 --preview
```

### Just change exposure (keep current mode)
```bash
python3 u20cam_linux_control.py --exposure-ms 10
```

### Just change gain (keep current mode)
```bash
python3 u20cam_linux_control.py --gain 16
```

### Specify camera device manually
```bash
python3 u20cam_linux_control.py -d /dev/video2 --status
```

## Command-Line Arguments

| Argument | Description |
|----------|-------------|
| `-d`, `--device` | Camera device path (default: auto-detect) |
| `--status` | Show current camera status and exit |
| `--mode {stream,trigger}` | Switch operating mode |
| `--exposure N` | Set exposure in UVC units (each unit = 100us) |
| `--exposure-ms N` | Set exposure in milliseconds (auto-converts to UVC units) |
| `--auto-exposure` | Restore auto exposure mode |
| `--gain N` | Set gain value |
| `--preview` | Show live preview after applying settings |
| `--preview-duration N` | Preview duration in seconds (default: 5) |

## Operating Modes Explained

### Stream Mode (default)

Camera outputs frames continuously at the configured frame rate.
This is the normal mode for video capture.

```bash
python3 u20cam_linux_control.py --mode stream
```

Controls set:
- `focus_automatic_continuous = 0`

### Trigger Mode

Camera waits for an external pulse on the FSIN pin. Each pulse triggers
one frame output. Used for synchronized multi-camera setups, machine vision,
and high-speed strobe applications.

```bash
python3 u20cam_linux_control.py --mode trigger
```

Controls set:
- `focus_automatic_continuous = 1`
- `auto_exposure = 1` (manual mode is required for trigger mode)

**Hardware setup for trigger mode:**
```
Host GPIO (3.3V-5V pulse) -> FSIN+
Host GND                  -> FSIN-
```

## Exposure Time Reference

UVC standard: `exposure_time_absolute` is in units of **100 microseconds**.

| UVC Value | Exposure Time | Max FPS |
|-----------|---------------|---------|
| 1         | 0.1 ms        | -       |
| 10        | 1 ms          | 1000    |
| 50        | 5 ms          | 200     |
| 83        | 8.3 ms        | ~120    |
| 100       | 10 ms         | 100     |
| 167       | 16.7 ms       | ~60     |
| 200       | 20 ms         | 50      |
| 333       | 33.3 ms       | ~30     |
| 1000      | 100 ms        | 10      |

For 120fps capture, the maximum exposure is ~8.3 ms.

The script accepts both UVC units and milliseconds:
```bash
python3 u20cam_linux_control.py --exposure 50       # UVC units
python3 u20cam_linux_control.py --exposure-ms 5     # milliseconds (same value)
```

## Gain Control

The U20CAM-9281M (OV9281 sensor) supports gain values typically in the range
0-64 (subject to firmware version).

**Important:** Gain may only have visible effect when **manual exposure mode is enabled**.
The script automatically warns you if you try to set gain while in auto exposure mode.

To set gain reliably, switch to manual exposure first:
```bash
python3 u20cam_linux_control.py --mode stream --exposure-ms 5 --gain 32
```

## Mode Switching Behavior

Switching modes automatically configures the prerequisites:

| From -> To | What the script does |
|-----------|----------------------|
| Auto -> Trigger | Sets `auto_exposure=1` (manual), then `focus_automatic_continuous=1` |
| Trigger -> Stream | Sets `focus_automatic_continuous=0` (exposure mode unchanged) |
| Stream -> Stream + manual exp | Sets `auto_exposure=1`, then `exposure_time_absolute=N` |

## Troubleshooting

### Permission denied on /dev/video0

Add your user to the `video` group:
```bash
sudo usermod -aG video $USER
# Log out and back in for the change to take effect
```

### Control name not found

Different kernel versions use different control names. The script tries both:
- `focus_automatic_continuous` (newer) / `focus_auto` (older)
- `auto_exposure` (newer) / `exposure_auto` (older)
- `exposure_time_absolute` (newer) / `exposure_absolute` (older)

If your camera uses a non-standard name, list all controls:
```bash
v4l2-ctl -d /dev/video0 -l
```

### Exposure value set, but image brightness does not change

Verify that exposure mode is actually `manual`:
```bash
python3 u20cam_linux_control.py --status
```

If `auto_exposure` is not `1`, manual exposure is being overridden by the auto algorithm.
Re-run with explicit mode:
```bash
python3 u20cam_linux_control.py --exposure-ms 5
# (this sets auto_exposure=1 first, then the value)
```

### Gain change has no visible effect

Most likely cause: camera is in auto exposure mode. The auto exposure algorithm
overrides gain based on scene brightness. Switch to manual exposure first:
```bash
python3 u20cam_linux_control.py --mode stream --exposure-ms 5 --gain 32
```

### Preview window shows no frames in trigger mode

Expected behavior. Trigger mode requires an external pulse on the FSIN pin
to produce a frame. Switch back to stream mode to verify the camera works:
```bash
python3 u20cam_linux_control.py --mode stream --preview
```

### Frame rate drops after setting long exposure

Frame rate is physically limited by exposure time:
- 8.3 ms exposure -> max ~120 fps
- 16.7 ms exposure -> max ~60 fps
- 33.3 ms exposure -> max ~30 fps

This is a hardware limit, not a script bug.

## Equivalent v4l2-ctl Commands

For reference, the underlying v4l2-ctl commands the script issues:

### Stream mode + manual exposure 5ms + gain 32
```bash
v4l2-ctl -d /dev/video0 -c focus_automatic_continuous=0
v4l2-ctl -d /dev/video0 -c auto_exposure=1
v4l2-ctl -d /dev/video0 -c exposure_time_absolute=50
v4l2-ctl -d /dev/video0 -c gain=32
```

### Trigger mode
```bash
v4l2-ctl -d /dev/video0 -c auto_exposure=1
v4l2-ctl -d /dev/video0 -c focus_automatic_continuous=1
```

### Restore auto exposure
```bash
v4l2-ctl -d /dev/video0 -c auto_exposure=3
```

### List all controls
```bash
v4l2-ctl -d /dev/video0 -l
```

## UVC Control Reference

| v4l2 Control | Purpose | Values |
|--------------|---------|--------|
| `focus_automatic_continuous` | Trigger mode switch (UVC AutoFocus) | 0=Stream, 1=Trigger |
| `auto_exposure` | Exposure mode | 1=Manual, 3=Aperture Priority (Auto) |
| `exposure_time_absolute` | Exposure time (100us units) | 1 to ~10000 |
| `gain` | Sensor gain | 0-64 |
| `brightness` | Brightness offset | model-dependent |

## Why "focus_automatic_continuous" Controls Trigger Mode

UVC standard does not define a dedicated "trigger mode" control. InnoMaker
firmware repurposes the `focus_automatic_continuous` control (originally
intended for auto-focus enable/disable) to switch between stream and trigger
modes. This is why the auto-focus control appears on a fixed-focus camera.
