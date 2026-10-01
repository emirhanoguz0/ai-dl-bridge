"""ai-dl-bridge uzerinden dosya indir — tum AI indirmelerinin tek kapiyi.

Kullanim:
    python kopru_indir.py <URL> [--kalite video|eniyi|endusuk|ses] [--kimlik AI_ADI] [--bekle]

--bekle verilirse indirme bitene dek ilerlemeyi yazdirir (aria2 JSON-RPC ile).
Sunucu acik degilse exe'yi --gizli kipte kendi baslatir.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

EXE_YOLU = Path(r"D:\Second_Brain\🏰 300-Projects\AI-Indirme-Koprusu\dist\ai-dl-bridge.exe")
BASLANGIC_PORT, PORT_DENEME = 8765, 20   # run.py bos_port_bul ile ayni aralik
ARIA2_PORT = 6800
INDIRME_KLASORU = Path.home() / "Downloads" / "ai-dl-bridge"
GECMIS_DOSYA = Path(os.environ.get("APPDATA") or Path.home()) \
    / "ai-dl-bridge" / "gecmis.json"
BEKLEME_SN = 3600


def _bridge_sunucusu_mu(port: int) -> bool:
    """Portta FastAPI bridge sunucusu mu var? (aria2'nin 6800'i gibi
    acik ama yanit vermeyen portlari ele — yalnizca FastAPI 422 doner.)"""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/indir", data=b"x",
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3)
        return False
    except urllib.error.HTTPError as e:
        return e.code == 422   # FastAPI doğrulama hatası = bizim sunucu
    except Exception:
        return False


def port_bul() -> int | None:
    """8765-8784 arasinda yanıt veren bridge sunucusunu bul."""
    for p in range(BASLANGIC_PORT, BASLANGIC_PORT + PORT_DENEME):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                continue
        if _bridge_sunucusu_mu(p):
            return p
    return None


def sunucu_hazirla() -> int:
    """Sunucu yoksa exe'yi gizli baslat, portu dondur."""
    port = port_bul()
    if port:
        return port
    if not EXE_YOLU.exists():
        sys.exit(f"HATA: {EXE_YOLU} bulunamadi — once exe'yi derle.")
    subprocess.Popen(
        ["cmd", "/c", "start", "", "/min", str(EXE_YOLU), "--gizli"],
        close_fds=True)
    for _ in range(30):
        time.sleep(1)
        port = port_bul()
        if port:
            return port
    sys.exit("HATA: bridge sunucusu 30 sn icinde acilmadi.")


def post_json(url: str, yuk: dict, zaman_asim: int = 120) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(yuk).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=zaman_asim) as r:
        return json.loads(r.read())


def aria2_cagri(yontem: str, params: list) -> dict:
    yuk = {"jsonrpc": "2.0", "id": 1, "method": f"aria2.{yontem}", "params": params}
    req = urllib.request.Request(
        f"http://127.0.0.1:{ARIA2_PORT}/jsonrpc",
        data=json.dumps(yuk).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            yanit = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"aria2 HTTP {e.code}") from e
    if "error" in yanit:
        raise RuntimeError(yanit["error"].get("message", "bilinmeyen hata"))
    return yanit["result"]


def yeni_dosya_bul(sure_sn: int = 120) -> Path | None:
    """İndirme klasöründe son N saniyede değişen en yeni dosyayı döndür."""
    if not INDIRME_KLASORU.exists():
        return None
    simdi = time.time()
    adaylar = [f for f in INDIRME_KLASORU.iterdir()
               if f.is_file() and simdi - f.stat().st_mtime < sure_sn]
    return max(adaylar, key=lambda f: f.stat().st_mtime) if adaylar else None


def gecmiste_bul(gid: str) -> dict | None:
    """Uygulamanin kalici gecmisinde gid'i ara (UI tamamlananlari oraya yazar)."""
    try:
        kayitlar = json.loads(GECMIS_DOSYA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for k in kayitlar:
        if k.get("gid") == gid:
            return k
    return None


def _tamam_mi_bul(gid: str, ek_sn: int = 12) -> Path | None:
    """gid kuyruktan dustukten sonra dosyayi bul: once kalici gecmis, sonra
    klasordeki en yeni dosya. UI'nin gecmis yazmasi icin kisa bir pay birakir."""
    son = time.time() + ek_sn
    while time.time() < son:
        kayit = gecmiste_bul(gid)
        if kayit and kayit.get("yol") and Path(kayit["yol"]).exists():
            return Path(kayit["yol"])
        dosya = yeni_dosya_bul()
        if dosya:
            return dosya
        time.sleep(2)
    return None


def bekle_gid(gid: str) -> int:
    """Indirme tamamlanana dek bekle; cikis kodu 0/1."""
    otomatik_devam_yapildi = False
    gid_kayboldu = 0
    baslangic = time.time()
    while time.time() - baslangic < BEKLEME_SN:
        try:
            durum = aria2_cagri("tellStatus", [gid])
        except RuntimeError as e:
            # gid temizlenmiş olabilir (küçük dosya anında biter) ya da
            # geçici RPC kesintisi — kalıcı geçmiş + klasörden doğrula
            gid_kayboldu += 1
            if gid_kayboldu >= 2:
                dosya = _tamam_mi_bul(gid)
                if dosya:
                    print(f"\nTAMAM: {dosya} ({dosya.stat().st_size:,} bayt)")
                    return 0
                print(f"\nHATA: gid sorgulanamadı ({e})")
                return 1
            time.sleep(2)
            continue
        gid_kayboldu = 0
        kod = durum.get("status", "error")
        tam = int(durum.get("completedLength", 0))
        top = int(durum.get("totalLength", 0))
        hiz = int(durum.get("downloadSpeed", 0))
        yuzde = round(100 * tam / top) if top else 0
        print(f"\r%{yuzde} · {hiz // 1024} KB/s", end="", flush=True)
        if kod == "complete":
            dosya = (durum.get("files") or [{}])[0].get("path", "")
            boyut = Path(dosya).stat().st_size if dosya and Path(dosya).exists() else tam
            print(f"\nTAMAM: {dosya} ({boyut:,} bayt)")
            return 0
        if kod in ("error", "removed"):
            print(f"\nHATA: durum={kod}")
            return 1
        if kod == "paused" and not otomatik_devam_yapildi:
            # sunucu politikasi buyuk dosyayi kuyruga almissa bir kez surdur
            try:
                aria2_cagri("unpause", [gid])
                otomatik_devam_yapildi = True
            except Exception:
                pass
        time.sleep(2)
    print("\nHATA: zaman asimi")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="ai-dl-bridge ile indir")
    ap.add_argument("link")
    ap.add_argument("--kalite", default="video",
                    choices=["video", "eniyi", "endusuk", "ses"])
    ap.add_argument("--kimlik", default="kimi")
    ap.add_argument("--bekle", action="store_true",
                    help="indirme bitene dek bekle ve ilerlemeyi goster")
    a = ap.parse_args()

    port = sunucu_hazirla()
    yanit = post_json(
        f"http://127.0.0.1:{port}/indir",
        {"link": a.link, "kimlik": a.kimlik, "kalite": a.kalite})
    print(json.dumps(yanit, ensure_ascii=False))

    if yanit.get("durum") in ("reddedildi",):
        return 1
    if a.bekle and yanit.get("id"):
        return bekle_gid(yanit["id"])
    print(f"Klasor: {INDIRME_KLASORU}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
