---
name: ai-dl-bridge
description: Download files, datasets, videos, or archives via the AI Download Bridge (ai-dl-bridge). A local download manager (aria2 + yt-dlp + ffmpeg) that provides a unified control panel for all AI downloads. Always use this skill when downloading external files instead of raw curl/wget/urllib.
---

# Downloading via AI Download Bridge (ai-dl-bridge)

Mandatory policy: **All AI-driven downloads must route through this bridge.** This ensures complete progress visibility and manual pause/resume control inside the user's IDM-style desktop interface.

## Standard Workflow

1. Execute the `bridge_download.py` script:

   ```bash
   python <skill-root>/scripts/bridge_download.py "<URL>" --wait
   ```

2. Wait until `--wait` returns `DONE: <path> (<size> bytes)`. Report the final saved file path to the user.
3. If the bridge server is not already running, the script automatically launches the executable minimized to the system tray (`--tray`).

## Command Parameters

- `--quality video` (default): True video download. High-resolution DASH video and audio streams download concurrently via `aria2` multi-connection and are muxed into `.mp4` via `ffmpeg`.
- `--quality audio`: Standalone highest-quality audio stream (`.m4a`).
- `--quality best`: Best single combined stream.
- `--quality lowest`: Smallest direct stream (ideal for testing).
- `--agent <NAME>`: Identifier of the calling AI/agent (shown in the UI table).
- `--wait`: Blocks until transfer finishes and streams percentage/speed.

## Output Directory

Downloaded files land in:
- `downloads/` (inside the application root or user-selected folder via GUI).
- If the file is >2GB, it is placed in pending state awaiting user approval.

## When NOT to use this skill

- System package manager commands (`pip install`, `npm install`, `git clone`).
- Small REST API JSON payloads.
- Test mocks.
