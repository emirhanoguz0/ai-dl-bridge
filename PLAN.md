# AI-DL-Bridge — Implementation Plan

Specification: `docs/2026-09-28-design.md` (Approved 2026-09-28)

## Phases
1. **Skeleton & Plan** — directory structure, dependencies, requirements.txt, PLAN.md ✅
2. **Core (Headless & Testable):**
   - `bridge/aria2_rpc.py` — aria2 JSON-RPC client (`addUri`, `tellStatus`, `pause`/`unpause`/`remove`, `globalSpeedLimit`) — pure Python, urllib
   - `bridge/resolver.py` — link classification (video sites list) + yt-dlp invocation (`yt-dlp --get-url --get-title --no-playlist -J`) — returns direct stream URL + title + estimated size; descriptive errors if missing/broken
   - `bridge/policy.py` — size safety policy: if size > 2GB → mark as "paused / awaiting approval"
   - `bridge/server.py` — FastAPI: `POST /download` (with backward-compatible `/indir`, dynamic port selection: 8765+, localhost-only)
   - `bridge/muxer.py` — background DASH video/audio stream muxing using bundled `ffmpeg`
3. **Unit Tests (Offline):** mock aria2 RPC responses, policy boundaries, resolver mock outputs
4. **Desktop UI (PyQt6):** system tray icon, interactive download list (title, progress %, speed, status color), click-to-expand action drawer (`Resume`/`Pause`/`Cancel`), context menu (speed limits, autostart, connection snippets, folder picker), footer summary status bar, 1-second polling timer
5. **Integration Tests:** live aria2 + local HTTP file server (localhost-to-localhost, no external internet needed)
6. **Packaging:** PyInstaller spec (`ai-dl-bridge.spec`) — single standalone portable exe bundling `aria2c`, `yt-dlp`, and `ffmpeg`

## Repository Structure
```
ai-dl-bridge/
├── docs/2026-09-28-design.md
├── docs/2026-09-29-ui-plan.md
├── docs/*.png
├── PLAN.md
├── requirements.txt
├── run.py
├── bridge/
│   ├── __init__.py
│   ├── aria2_rpc.py
│   ├── muxer.py
│   ├── paths.py
│   ├── policy.py
│   ├── resolver.py
│   └── server.py
├── ui/
│   ├── __init__.py
│   ├── app.py
│   ├── autostart.py
│   ├── daemon.py
│   └── viewmodel.py
├── tools/            (aria2c.exe, yt-dlp.exe, ffmpeg.exe — portable companion binaries)
└── tests/
    ├── test_core.py
    ├── test_integration.py
    ├── test_ui_core.py
    └── test_video.py
```

## Architectural Notes
- `yt-dlp` never performs file downloads; it only extracts metadata and stream URLs (`--get-url`). All downloads are routed through `aria2c` for unified throttling, pausing, and resuming.
- All errors are formatted as actionable, descriptive JSON responses for AI agents.
- Package name: `ai-dl-bridge` (clean open-source standard).
