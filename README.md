# ai-dl-bridge

A tiny Windows app that lets **AI agents download files and real videos through
one local door** — while you keep full visibility and control, IDM-style.

![screenshot](docs/ekran-v4-gecmis.png)

## Why

AI assistants can fetch small text resources directly, but large files,
YouTube videos, and anything that needs merging or a queue belong in a tool you
control: your own downloader with a progress window, speed limits, pause/resume,
and a persistent history. ai-dl-bridge is that tool. Any AI (or script) POSTs a
link to `http://127.0.0.1:8765/indir`; the download appears in the window,
streams through aria2 at full speed, and lands in your chosen folder.

## Features

- **One door for AIs** — single local HTTP endpoint (`POST /indir`), no auth
  needed on localhost.
- **Real YouTube video** — modern YouTube serves video and audio as separate
  DASH streams. The bridge resolves the best pair, downloads both through
  aria2, and merges them with bundled ffmpeg into a single `.mp4`
  (`-c copy`, no re-encoding). Verified up to 2560×1440@60.
- **IDM-style window** — pastel, frameless mini window: Resume / Pause / Remove
  / Folder buttons, global speed limit, clickable column headers
  (Name / Size / Date) with sort directions, persistent download history with
  size + timestamp stamps.
- **Persistent history** — completed downloads survive restarts
  (`%APPDATA%/ai-dl-bridge/gecmis.json`, capped at 200 entries).
- **Merge jobs survive restarts** — interrupted video merges resume on launch.
- **Tray-first** — closing the window keeps it running in the tray; optional
  autostart with Windows.
- **Safety policy** — files over 2 GB wait for your approval instead of
  starting automatically.

## How AIs use it

```bash
curl -X POST http://127.0.0.1:8765/indir \
  -H "Content-Type: application/json" \
  -d '{"link": "https://www.youtube.com/watch?v=...", "kimlik": "my-ai", "kalite": "video"}'
```

`kalite`: `video` (default — best video+audio merged), `ses` (best audio m4a),
`eniyi` (best single stream), `endusuk` (smallest — quick tests).

A ready-made helper for agents lives in
[`skills/ai-indirme-koprusu/`](skills/ai-indirme-koprusu/SKILL.md):
it waits for completion, auto-resumes policy-paused downloads, and verifies the
file on disk.

## Build & run

```bash
pip install -r requirements.txt

# put the three binaries into tools/ first — see tools/README.md
python run.py            # windowed
python run.py --gizli    # start hidden in the tray

python -m pytest tests/  # 48 tests
python -m PyInstaller ai-dl-bridge.spec --noconfirm   # one-file exe in dist/
```

## Stack

Python 3.10+, PyQt6, FastAPI + uvicorn, aria2 (JSON-RPC), yt-dlp, ffmpeg —
all bundled into a single `.exe` (129 MB, mostly ffmpeg).

## License

MIT — see [LICENSE](LICENSE).
