"""FastAPI gateway — Single Door. AI agents POST to /download (or legacy /indir)."""
from __future__ import annotations

import json
import os
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field, model_validator

from . import muxer
birlestirici = muxer  # backward compatibility alias
from .aria2_rpc import Aria2RPC, Aria2Error
from .paths import indirme_koku
from .policy import degerlendir
from .resolver import VideoCozumHatasi, coz, coz_video, temiz_ad, video_sitesi_mi

BASLANGIC_PORT = 8765
SETTINGS_FILE = Path(os.environ.get("APPDATA") or Path.home()) \
    / "ai-dl-bridge" / "settings.json"
LEGACY_SETTINGS_FILE = Path(os.environ.get("APPDATA") or Path.home()) \
    / "ai-dl-bridge" / "ayarlar.json"
AYARLAR_DOSYASI = SETTINGS_FILE


def _ayarlanmis_klasor() -> Path:
    """User-configured folder if previously set, otherwise downloads/."""
    for cfg in (SETTINGS_FILE, LEGACY_SETTINGS_FILE):
        try:
            if cfg.exists():
                yol = Path(json.loads(cfg.read_text(encoding="utf-8"))
                           .get("indirme_klasoru", ""))
                if yol and yol.is_dir():
                    return yol
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    return indirme_koku()


INDIRME_KLASORU = _ayarlanmis_klasor()
INDIRME_KLASORU.mkdir(parents=True, exist_ok=True)


def klasoru_degistir(yeni: Path) -> None:
    """Activates and persists new download folder."""
    global INDIRME_KLASORU
    INDIRME_KLASORU = Path(yeni)
    INDIRME_KLASORU.mkdir(parents=True, exist_ok=True)
    try:
        AYARLAR_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
        AYARLAR_DOSYASI.write_text(
            json.dumps({"indirme_klasoru": str(INDIRME_KLASORU)},
                       ensure_ascii=False, indent=1),
            encoding="utf-8")
    except OSError:
        pass


def bos_port_bul(baslangic: int = BASLANGIC_PORT, deneme: int = 20) -> int:
    """Returns the first available port starting from baslangic (spec §1)."""
    for port in range(baslangic, baslangic + deneme):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"{deneme} ports tried, all in use")


class DownloadRequest(BaseModel):
    url: str = ""
    agent: str = Field(default="anonymous", max_length=64)
    quality: str = Field(default="video", pattern="^(video|best|eniyi|lowest|endusuk|audio|ses)$")

    # Legacy Turkish parameter aliases
    link: str | None = None
    kimlik: str | None = None
    kalite: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _resolve_aliases(cls, data):
        if isinstance(data, dict):
            if not data.get("url") and data.get("link"):
                data["url"] = data["link"]
            if not data.get("agent") and data.get("kimlik"):
                data["agent"] = data["kimlik"]
            if not data.get("quality") and data.get("kalite"):
                data["quality"] = data["kalite"]
        return data

    def target_url(self) -> str:
        return self.url or self.link or ""

    def target_agent(self) -> str:
        return self.agent or self.kimlik or "anonymous"

    def normalized_quality(self) -> str:
        q = self.quality or self.kalite or "video"
        if q == "eniyi":
            return "best"
        if q == "endusuk":
            return "lowest"
        if q == "ses":
            return "audio"
        return q


IndirmeIstegi = DownloadRequest  # backward compatibility alias


def _cevap(status: str, id: str | None = None, reason: str | None = None) -> dict:
    durum_map = {"accepted": "kabul", "pending": "beklemede", "rejected": "reddedildi"}
    resp = {
        "status": status,
        "durum": durum_map.get(status, status),
    }
    if id is not None:
        resp["id"] = id
    if reason is not None:
        resp["reason"] = reason
        resp["sebep"] = reason
    return resp


def _video_indir(istek: DownloadRequest, rpc: Aria2RPC) -> dict:
    """True video: separate DASH streams downloaded, ffmpeg muxes in GUI."""
    url = istek.target_url()
    try:
        plan = coz_video(url)
    except VideoCozumHatasi as e:
        return _cevap(status="rejected", reason=str(e))

    karar = degerlendir(plan.toplam_boyut)
    if not karar.uygun and not karar.beklemede:
        return _cevap(status="rejected", reason=karar.sebep)
    bekle = karar.beklemede

    ad = temiz_ad(plan.baslik)
    video_parca = f"{ad} [part1].{plan.video_uzanti}"
    hedef = str(INDIRME_KLASORU / f"{ad}.{plan.video_uzanti}")
    try:
        gid_v = rpc.add_uri(plan.video_url, str(INDIRME_KLASORU),
                            out_name=video_parca, paused=bekle)
        gid_a = None
        ses_parca = None
        if plan.ses_url:
            ses_parca = f"{ad} [part2].{plan.ses_uzanti}"
            gid_a = rpc.add_uri(plan.ses_url, str(INDIRME_KLASORU),
                                out_name=ses_parca, paused=bekle)
    except Aria2Error as e:
        return _cevap(status="rejected", reason=str(e))

    muxer.add_job({
        "anahtar": f"{gid_v}-{int(time.time())}",
        "video_gid": gid_v, "ses_gid": gid_a,
        "video_yol": str(INDIRME_KLASORU / video_parca),
        "ses_yol": str(INDIRME_KLASORU / ses_parca) if ses_parca else None,
        "hedef": hedef, "baslik": ad,
        "boyut": plan.toplam_boyut, "deneme": 0,
    })
    if bekle:
        return _cevap(status="pending", reason=karar.sebep, id=gid_v)
    return _cevap(status="accepted", id=gid_v)


def uygulama_yarat(rpc: Aria2RPC) -> FastAPI:
    app = FastAPI(title="ai-dl-bridge", docs_url=None, redoc_url=None)

    @app.post("/download")
    @app.post("/indir")
    def indir(istek: DownloadRequest) -> dict:
        url = istek.target_url()
        kalite = istek.normalized_quality()
        if kalite == "video" and video_sitesi_mi(url):
            return _video_indir(istek, rpc)

        try:
            plan = coz(url, kalite=kalite)
        except VideoCozumHatasi as e:
            return _cevap(status="rejected", reason=str(e))

        karar = degerlendir(plan.boyut)
        if not karar.uygun and not karar.beklemede:
            return _cevap(status="rejected", reason=karar.sebep)

        bekle = karar.beklemede
        try:
            gid = rpc.add_uri(plan.link, str(INDIRME_KLASORU),
                              out_name=temiz_ad(plan.baslik) if plan.video_mu else None,
                              paused=bekle)
        except Aria2Error as e:
            return _cevap(status="rejected", reason=str(e))

        if bekle:
            return _cevap(status="pending", reason=karar.sebep, id=gid)
        return _cevap(status="accepted", id=gid)

    return app

