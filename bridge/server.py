"""FastAPI sunucusu — Tek Kapı. AI'lar sadece POST /indir konuşur."""
from __future__ import annotations

import json
import os
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

from . import birlestirici
from .aria2_rpc import Aria2RPC, Aria2Error
from .paths import indirme_koku
from .policy import degerlendir
from .resolver import VideoCozumHatasi, coz, coz_video, temiz_ad, video_sitesi_mi

BASLANGIC_PORT = 8765
AYARLAR_DOSYASI = Path(os.environ.get("APPDATA") or Path.home()) \
    / "ai-dl-bridge" / "ayarlar.json"


def _ayarlanmis_klasor() -> Path:
    """Kullanıcı daha önce klasör seçtiyse onu, yoksa uygulama içi downloads/'ı."""
    try:
        yol = Path(json.loads(AYARLAR_DOSYASI.read_text(encoding="utf-8"))
                   .get("indirme_klasoru", ""))
        if yol and yol.is_dir():
            return yol
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return indirme_koku()


INDIRME_KLASORU = _ayarlanmis_klasor()
INDIRME_KLASORU.mkdir(parents=True, exist_ok=True)


def klasoru_degistir(yeni: Path) -> None:
    """Yeni indirme klasörünü etkinleştirir ve kalıcı olarak kaydeder."""
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
    """Başlangıç portundan itibaren ilk boş portu döner (spec §1)."""
    for port in range(baslangic, baslangic + deneme):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"{deneme} port denendi, hepsi dolu")


class IndirmeIstegi(BaseModel):
    link: str
    kimlik: str = Field(default="anonim", max_length=64)
    kalite: str = Field(default="video", pattern="^(video|eniyi|endusuk|ses)$")


def _video_indir(istek: IndirmeIstegi, rpc: Aria2RPC) -> dict:
    """Gerçek video: DASH parçaları ayrı iner, GUI tarafında ffmpeg birleştirir."""
    try:
        plan = coz_video(istek.link)
    except VideoCozumHatasi as e:
        return {"durum": "reddedildi", "sebep": str(e)}

    karar = degerlendir(plan.toplam_boyut)
    if not karar.uygun and not karar.beklemede:
        return {"durum": "reddedildi", "sebep": karar.sebep}
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
        return {"durum": "reddedildi", "sebep": str(e)}

    birlestirici.is_ekle({
        "anahtar": f"{gid_v}-{int(time.time())}",
        "video_gid": gid_v, "ses_gid": gid_a,
        "video_yol": str(INDIRME_KLASORU / video_parca),
        "ses_yol": str(INDIRME_KLASORU / ses_parca) if ses_parca else None,
        "hedef": hedef, "baslik": ad,
        "boyut": plan.toplam_boyut, "deneme": 0,
    })
    if bekle:
        return {"durum": "beklemede", "sebep": karar.sebep, "id": gid_v}
    return {"durum": "kabul", "id": gid_v}


def uygulama_yarat(rpc: Aria2RPC) -> FastAPI:
    app = FastAPI(title="ai-dl-bridge", docs_url=None, redoc_url=None)

    @app.post("/indir")
    def indir(istek: IndirmeIstegi) -> dict:
        if istek.kalite == "video" and video_sitesi_mi(istek.link):
            return _video_indir(istek, rpc)

        try:
            plan = coz(istek.link, kalite=istek.kalite)
        except VideoCozumHatasi as e:
            return {"durum": "reddedildi", "sebep": str(e)}

        karar = degerlendir(plan.boyut)
        if not karar.uygun and not karar.beklemede:
            return {"durum": "reddedildi", "sebep": karar.sebep}

        bekle = karar.beklemede
        try:
            gid = rpc.add_uri(plan.link, str(INDIRME_KLASORU),
                              out_name=temiz_ad(plan.baslik) if plan.video_mu else None,
                              paused=bekle)
        except Aria2Error as e:
            return {"durum": "reddedildi", "sebep": str(e)}

        if bekle:
            return {"durum": "beklemede", "sebep": karar.sebep, "id": gid}
        return {"durum": "kabul", "id": gid}

    return app
