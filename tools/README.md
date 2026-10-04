# Bundled Binaries (`tools/`)

The three companion binaries in this folder are portable standalone executables excluded from version control (`.gitignore`) to comply with GitHub file size guidelines:

| Binary | Recommended Source | Role |
|---|---|---|
| `aria2c.exe` | [aria2 Releases](https://github.com/aria2/aria2/releases) (win-64bit) | Multi-connection download engine & JSON-RPC daemon |
| `yt-dlp.exe` | [yt-dlp Releases](https://github.com/yt-dlp/yt-dlp/releases) (`yt-dlp.exe`) | Video metadata & direct stream URL resolver |
| `ffmpeg.exe` | [BtbN FFmpeg Builds](https://github.com/BtbN/FFmpeg-Builds/releases) (from `bin/ffmpeg.exe`) | Lossless DASH audio/video muxer (`-c copy`) |

## Setup Notes

1. Place the three `.exe` files directly into this `tools/` directory.
2. All three binaries are portable and require no installer.
3. While `aria2c` and `ffmpeg` can also be resolved from the system `PATH`, bundling them into `tools/` ensures seamless PyInstaller packaging (`ai-dl-bridge.spec`) into a single standalone `.exe`.
4. To regenerate application icons: `python tools/generate_logo.py`.
