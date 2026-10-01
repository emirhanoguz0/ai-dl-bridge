"""Parça birleştirme — indirilen video+ses parçalarını ffmpeg ile mp4 yapar.

Sunucu "video" kalitesinde iki parçayı aria2 kuyruğuna koyar ve buraya bir iş
kayıt bırakır. GUI her yenilemede (1 sn) bekleyen işleri tarar; iki parça da
diskte eksiksizse ffmpeg -c copy ile birleştirir, parçaları siler, biten satırı
geçmişe işlemek için çağırana bildirir.

İş kaydı: %APPDATA%/ai-dl-bridge/birlesme.json
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .paths import paket_koku

IS_DOSYASI = Path(os.environ.get("APPDATA") or Path.home()) \
    / "ai-dl-bridge" / "birlesme.json"
MAKS_DENEME = 3


def ffmpeg_yolu() -> str | None:
    """Gömülü ffmpeg.exe (tools/), yoksa PATH'tekini döner."""
    yerel = paket_koku() / "tools" / "ffmpeg.exe"
    if yerel.exists():
        return str(yerel)
    return shutil.which("ffmpeg")


def is_ekle(kayit: dict) -> None:
    isler = [i for i in isleri_oku() if i.get("anahtar") != kayit.get("anahtar")]
    isler.append(kayit)
    _yaz(isler)


def isleri_oku() -> list[dict]:
    try:
        veri = json.loads(IS_DOSYASI.read_text(encoding="utf-8"))
        return veri if isinstance(veri, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def parca_gidleri() -> set[str]:
    """GUI'nin parça satırlarını 'tamamlandı' saymaması için parça gid'leri."""
    gidler = set()
    for i in isleri_oku():
        for k in ("video_gid", "ses_gid"):
            if i.get(k):
                gidler.add(i[k])
    return gidler


def _yaz(isler: list[dict]) -> None:
    try:
        IS_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
        IS_DOSYASI.write_text(json.dumps(isler, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    except OSError:
        pass


def _is_tamamlandi(job: dict) -> bool:
    """İki parça da diskte ve yarım indirme artığı (.aria2) kalmadıysa True."""
    parcalar = [job["video_yol"]] + ([job["ses_yol"]] if job.get("ses_yol") else [])
    for yol in parcalar:
        p = Path(yol)
        if not p.exists() or Path(str(yol) + ".aria2").exists():
            return False
    return True


def _is_canli_mi(rpc, job: dict) -> bool:
    """Parçalardan en az biri hâlâ aria2 kuyruğunda aktif/bekliyorsa True."""
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
    """ffmpeg -c copy ile birleştirir; tek parçada dosyayı yerine taşır."""
    hedef = Path(job["hedef"])
    hedef.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_yolu()
    if job.get("ses_yol") and Path(job["ses_yol"]).exists():
        if not ff:
            raise RuntimeError("ffmpeg bulunamadı — tools/ffmpeg.exe eksik")
        out = subprocess.run(
            [ff, "-y", "-hide_banner", "-loglevel", "error",
             "-i", job["video_yol"], "-i", job["ses_yol"],
             "-c", "copy", "-movflags", "+faststart", str(hedef)],
            capture_output=True, text=True, timeout=600)
        if out.returncode != 0 or not hedef.exists():
            raise RuntimeError(f"ffmpeg başarısız: {(out.stderr or '').strip()[:300]}")
        Path(job["video_yol"]).unlink(missing_ok=True)
        Path(job["ses_yol"]).unlink(missing_ok=True)
    else:
        Path(job["video_yol"]).replace(hedef)


def bekleyenleri_isle(rpc, biten_callback=None) -> list[dict]:
    """Tamamlanan işleri birleştirir; (kayıt, hata) listesi döner.

    biten_callback(job) başarılı birleşmede çağrılır (GUI geçmiş satırı ekler).
    """
    from .aria2_rpc import Aria2Error
    sonuclar = []
    for job in isleri_oku():
        anahtar = job.get("anahtar")
        try:
            if not _is_tamamlandi(job):
                if not _is_canli_mi(rpc, job):
                    # parça kaybolmuş ve kuyrukta yok → iş ölü, temizle
                    for k in ("video_yol", "ses_yol"):
                        if job.get(k):
                            Path(job[k]).unlink(missing_ok=True)
                            Path(job[k] + ".aria2").unlink(missing_ok=True)
                    is_ekle_sil(anahtar)
                    sonuclar.append((job, "iptal: parça kayboldu"))
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
            sonuclar.append((job, "tamam"))
        except Exception as e:  # birleştirme hatası — sınırlı tekrar dene
            job["deneme"] = int(job.get("deneme", 0)) + 1
            isler = [i for i in isleri_oku() if i.get("anahtar") != anahtar]
            if job["deneme"] >= MAKS_DENEME:
                for k in ("video_yol", "ses_yol"):
                    if job.get(k):
                        Path(job[k]).unlink(missing_ok=True)
            else:
                isler.append(job)
            _yaz(isler)
            sonuclar.append((job, f"hata: {e}"))
    return sonuclar


def is_ekle_sil(anahtar: str) -> None:
    _yaz([i for i in isleri_oku() if i.get("anahtar") != anahtar])
