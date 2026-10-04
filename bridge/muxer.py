"""Media muxer — merges downloaded video + audio DASH streams into mp4 using FFmpeg.

The server queues two separate streams in aria2 for "video" quality jobs and logs a record.
The GUI polls pending jobs on each refresh (1s); when both streams exist completely on disk
without .aria2 residue, it muxes them losslessly with `ffmpeg -c copy`, cleans up temporary
parts, and notifies the caller to record the completed download in history.

Job registry: %APPDATA%/ai-dl-bridge/jobs.json (with legacy birlesme.json fallback)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .paths import paket_koku

JOBS_FILE = Path(os.environ.get("APPDATA") or Path.home()) \
    / "ai-dl-bridge" / "jobs.json"
LEGACY_JOBS_FILE = Path(os.environ.get("APPDATA") or Path.home()) \
    / "ai-dl-bridge" / "birlesme.json"
MAX_ATTEMPTS = 3


def ffmpeg_yolu() -> str | None:
    """Returns path to embedded tools/ffmpeg.exe, or system PATH binary."""
    yerel = paket_koku() / "tools" / "ffmpeg.exe"
    if yerel.exists():
        return str(yerel)
    return shutil.which("ffmpeg")


def is_ekle(kayit: dict) -> None:
    """Appends a new muxing job."""
    isler = [i for i in isleri_oku() if i.get("anahtar") != kayit.get("anahtar")]
    isler.append(kayit)
    _yaz(isler)


def isleri_oku() -> list[dict]:
    """Reads pending muxing jobs from disk."""
    for dosya in (JOBS_FILE, LEGACY_JOBS_FILE):
        try:
            if dosya.exists():
                veri = json.loads(dosya.read_text(encoding="utf-8"))
                if isinstance(veri, list):
                    return veri
        except (OSError, json.JSONDecodeError):
            pass
    return []


def parca_gidleri() -> set[str]:
    """Returns set of all part GIDs so GUI does not treat partial streams as finished downloads."""
    gidler = set()
    for i in isleri_oku():
        for k in ("video_gid", "ses_gid"):
            if i.get(k):
                gidler.add(i[k])
    return gidler


def _yaz(isler: list[dict]) -> None:
    try:
        JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        JOBS_FILE.write_text(json.dumps(isler, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    except OSError:
        pass


def _is_tamamlandi(job: dict) -> bool:
    """True if both streams exist on disk and no .aria2 residue exists."""
    parcalar = [job["video_yol"]] + ([job["ses_yol"]] if job.get("ses_yol") else [])
    for yol in parcalar:
        p = Path(yol)
        if not p.exists() or Path(str(yol) + ".aria2").exists():
            return False
    return True


def _is_canli_mi(rpc, job: dict) -> bool:
    """True if at least one part is still active/waiting/paused in aria2 queue."""
    from .aria2_rpc import Aria2Error
    for k in ("video_gid", "ses_gid"):
        gid = job.get(k)
        if not gid:
            continue
        try:
            durum = rpc.tell_status(gid)
            if durum.get("status") in ("active", "waiting", "paused"):
                return True
        except Aria2Error:
            continue
    return False


def _birlestir(job: dict) -> None:
    """Muxes streams via ffmpeg -c copy; moves single stream directly if audio not needed."""
    hedef = Path(job["hedef"])
    hedef.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_yolu()
    if job.get("ses_yol") and Path(job["ses_yol"]).exists():
        if not ff:
            raise RuntimeError("ffmpeg not found — tools/ffmpeg.exe missing")
        out = subprocess.run(
            [ff, "-y", "-hide_banner", "-loglevel", "error",
             "-i", job["video_yol"], "-i", job["ses_yol"],
             "-c", "copy", "-movflags", "+faststart", str(hedef)],
            capture_output=True, text=True, timeout=600)
        if out.returncode != 0 or not hedef.exists():
            raise RuntimeError(f"ffmpeg failed: {(out.stderr or '').strip()[:300]}")
        Path(job["video_yol"]).unlink(missing_ok=True)
        Path(job["ses_yol"]).unlink(missing_ok=True)
    else:
        Path(job["video_yol"]).replace(hedef)


def bekleyenleri_isle(rpc, biten_callback=None) -> list[tuple[dict, str]]:
    """Muxes completed jobs; returns list of (job, status) tuples.

    biten_callback(job) is called upon successful muxing (GUI adds history row).
    """
    from .aria2_rpc import Aria2Error
    sonuclar = []
    for job in isleri_oku():
        anahtar = job.get("anahtar")
        try:
            if not _is_tamamlandi(job):
                if not _is_canli_mi(rpc, job):
                    for k in ("video_yol", "ses_yol"):
                        if job.get(k):
                            Path(job[k]).unlink(missing_ok=True)
                            Path(job[k] + ".aria2").unlink(missing_ok=True)
                    is_ekle_sil(anahtar)
                    sonuclar.append((job, "cancelled: part missing"))
                continue
            _birlestir(job)
            is_ekle_sil(anahtar)
            for k in ("video_gid", "ses_gid"):
                if job.get(k):
                    try:
                        rpc.remove_download_result(job[k])
                    except Aria2Error:
                        pass
            if biten_callback:
                biten_callback(job)
            sonuclar.append((job, "done"))
        except Exception as e:
            job["deneme"] = int(job.get("deneme", 0)) + 1
            isler = [i for i in isleri_oku() if i.get("anahtar") != anahtar]
            if job["deneme"] >= MAX_ATTEMPTS:
                for k in ("video_yol", "ses_yol"):
                    if job.get(k):
                        Path(job[k]).unlink(missing_ok=True)
            else:
                isler.append(job)
            _yaz(isler)
            sonuclar.append((job, f"error: {e}"))
    return sonuclar


def is_ekle_sil(anahtar: str) -> None:
    _yaz([i for i in isleri_oku() if i.get("anahtar") != anahtar])


# English alias names
add_job = is_ekle
read_jobs = isleri_oku
part_gids = parca_gidleri
process_pending = bekleyenleri_isle
remove_job = is_ekle_sil
