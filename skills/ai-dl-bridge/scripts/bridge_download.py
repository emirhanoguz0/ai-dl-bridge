"""Download files via ai-dl-bridge — Single doorway for all AI downloads.

Usage:
    python bridge_download.py <URL> [--quality video|best|lowest|audio] [--agent AI_NAME] [--wait]

If --wait is provided, streams progress until completion via aria2 JSON-RPC.
If server is not running, launches the application minimized to tray automatically.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

START_PORT, PORT_ATTEMPTS = 8765, 20
ARIA2_PORT = 6800


def _project_root() -> Path | None:
    """Finds project root by locating run.py/bridge upwards."""
    for candidate in [Path(__file__).resolve()] + list(Path(__file__).resolve().parents):
        if (candidate / "run.py").exists() and (candidate / "bridge").is_dir():
            return candidate
    return None


def _find_exe() -> Path | None:
    """Locates compiled ai-dl-bridge.exe from dist or PATH/APPDATA."""
    root = _project_root()
    if root:
        dist_exe = root / "dist" / "ai-dl-bridge.exe"
        if dist_exe.is_file():
            return dist_exe
    in_path = shutil.which("ai-dl-bridge.exe")
    if in_path:
        return Path(in_path)
    appdata = Path(os.environ.get("APPDATA") or Path.home()) / "ai-dl-bridge" / "ai-dl-bridge.exe"
    if appdata.is_file():
        return appdata
    return None


def _default_folder() -> Path:
    root = _project_root()
    if root:
        return root / "downloads"
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "downloads"
    return Path.cwd() / "downloads"


DOWNLOAD_FOLDER = _default_folder()
HISTORY_FILE = Path(os.environ.get("APPDATA") or Path.home()) \
    / "ai-dl-bridge" / "history.json"
LEGACY_HISTORY_FILE = Path(os.environ.get("APPDATA") or Path.home()) \
    / "ai-dl-bridge" / "gecmis.json"
WAIT_TIMEOUT = 3600


def _is_bridge_server(port: int) -> bool:
    """Checks if the port is running the FastAPI bridge (returns 422 on invalid json body)."""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/download", data=b"x",
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3)
        return False
    except urllib.error.HTTPError as e:
        return e.code == 422
    except Exception:
        return False


def find_port() -> int | None:
    """Finds responsive bridge server between 8765-8784."""
    for p in range(START_PORT, START_PORT + PORT_ATTEMPTS):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                continue
        if _is_bridge_server(p):
            return p
    return None


def ensure_server() -> int:
    """Starts server in background if not running, returns active port."""
    port = find_port()
    if port:
        return port

    exe = _find_exe()
    if exe and exe.exists():
        subprocess.Popen(
            ["cmd", "/c", "start", "", "/min", str(exe), "--tray"],
            close_fds=True)
    else:
        root = _project_root()
        if root and (root / "run.py").is_file():
            subprocess.Popen(
                [sys.executable, str(root / "run.py"), "--tray"],
                close_fds=True)
        else:
            sys.exit("ERROR: ai-dl-bridge.exe or run.py not found — build or set up the environment first.")

    for _ in range(30):
        time.sleep(1)
        port = find_port()
        if port:
            return port
    sys.exit("ERROR: bridge server did not start within 30 seconds.")


def post_json(url: str, payload: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def aria2_call(method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": f"aria2.{method}", "params": params}
    req = urllib.request.Request(
        f"http://127.0.0.1:{ARIA2_PORT}/jsonrpc",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"aria2 HTTP {e.code}") from e
    if "error" in res:
        raise RuntimeError(res["error"].get("message", "unknown error"))
    return res["result"]


def find_recent_file(max_age_sec: int = 120) -> Path | None:
    """Returns the most recent file in download folder modified within max_age_sec."""
    if not DOWNLOAD_FOLDER.exists():
        return None
    now = time.time()
    candidates = [f for f in DOWNLOAD_FOLDER.iterdir()
                  if f.is_file() and now - f.stat().st_mtime < max_age_sec]
    return max(candidates, key=lambda f: f.stat().st_mtime) if candidates else None


def find_in_history(gid: str) -> dict | None:
    """Searches for GID in persisted history."""
    for f in (HISTORY_FILE, LEGACY_HISTORY_FILE):
        try:
            if f.exists():
                records = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(records, list):
                    for r in records:
                        if r.get("gid") == gid:
                            return r
        except (OSError, json.JSONDecodeError):
            pass
    return None


def _find_completed_file(gid: str, extra_sec: int = 12) -> Path | None:
    deadline = time.time() + extra_sec
    while time.time() < deadline:
        record = find_in_history(gid)
        if record and record.get("yol") and Path(record["yol"]).exists():
            return Path(record["yol"])
        file = find_recent_file()
        if file:
            return file
        time.sleep(2)
    return None


def wait_for_gid(gid: str) -> int:
    """Waits until download finishes; returns exit code 0 or 1."""
    auto_resumed = False
    gid_missing_count = 0
    started_at = time.time()
    while time.time() - started_at < WAIT_TIMEOUT:
        try:
            status = aria2_call("tellStatus", [gid])
        except RuntimeError as e:
            gid_missing_count += 1
            if gid_missing_count >= 2:
                file = _find_completed_file(gid)
                if file:
                    print(f"\nDONE: {file} ({file.stat().st_size:,} bytes)")
                    return 0
                print(f"\nERROR: GID cannot be queried ({e})")
                return 1
            time.sleep(2)
            continue
        gid_missing_count = 0
        code = status.get("status", "error")
        done = int(status.get("completedLength", 0))
        total = int(status.get("totalLength", 0))
        speed = int(status.get("downloadSpeed", 0))
        pct = round(100 * done / total) if total else 0
        print(f"\r{pct}% · {speed // 1024} KB/s", end="", flush=True)
        if code == "complete":
            file_path = (status.get("files") or [{}])[0].get("path", "")
            size = Path(file_path).stat().st_size if file_path and Path(file_path).exists() else done
            print(f"\nDONE: {file_path} ({size:,} bytes)")
            return 0
        if code in ("error", "removed"):
            print(f"\nERROR: status={code}")
            return 1
        if code == "paused" and not auto_resumed:
            try:
                aria2_call("unpause", [gid])
                auto_resumed = True
            except Exception:
                pass
        time.sleep(2)
    print("\nERROR: Timeout exceeded")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Download files via ai-dl-bridge")
    ap.add_argument("url", nargs="?", help="Download URL")
    ap.add_argument("--url", dest="url_opt", help="Download URL (flag)")
    ap.add_argument("--quality", "--kalite", default="video",
                    choices=["video", "best", "eniyi", "lowest", "endusuk", "audio", "ses"])
    ap.add_argument("--agent", "--kimlik", default="agent")
    ap.add_argument("--wait", "--bekle", action="store_true",
                    help="wait until download completes and stream progress")
    a = ap.parse_args()

    target_url = a.url or a.url_opt
    if not target_url:
        ap.error("URL is required (positional or --url)")

    port = ensure_server()
    resp = post_json(
        f"http://127.0.0.1:{port}/download",
        {"url": target_url, "agent": a.agent, "quality": a.quality})
    print(json.dumps(resp, ensure_ascii=False))

    status = resp.get("status") or resp.get("durum")
    if status in ("rejected", "reddedildi"):
        return 1
    if (a.wait or a.bekle) and resp.get("id"):
        return wait_for_gid(resp["id"])
    print(f"Folder: {DOWNLOAD_FOLDER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
