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
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASLANGIC_PORT, PORT_DENEME = 8765, 20   # run.py bos_port_bul ile ayni aralik
ARIA2_PORT = 6800


def _proje_koku() -> Path | None:
    """Proje kökünü run.py/bridge işaretleriyle yukarı doğru arar."""
    for aday in [Path(__file__).resolve()] + list(Path(__file__).resolve().parents):
        if (aday / "run.py").exists() and (aday / "bridge").is_dir():
            return aday
    return None


def _exe_bul() -> Path | None:
    """Derlenmiş exe'yi proje dist klasöründen veya sistemden arar."""
    kok = _proje_koku()
    if kok:
        dist_exe = kok / "dist" / "ai-dl-bridge.exe"
        if dist_exe.is_file():
            return dist_exe
    yoldaki = shutil.which("ai-dl-bridge.exe")
    if yoldaki:
        return Path(yoldaki)
    appdata = Path(os.environ.get("APPDATA") or Path.home()) / "ai-dl-bridge" / "ai-dl-bridge.exe"
    if appdata.is_file():
        return appdata
    return None


def _varsayilan_klasor() -> Path:
    kok = _proje_koku()
    if kok:
        return kok / "downloads"
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "downloads"
    return Path.cwd() / "downloads"


INDIRME_KLASORU = _varsayilan_klasor()
GECMIS_DOSYA = Path(os.environ.get("APPDATA") or Path.home()) \
    / "ai-dl-bridge" / "gecmis.json"
BEKLEME_SN = 3600


def _bridge_sunucusu_mu(port: int) -> bool:
    """Portta FastAPI bridge sunucusu mu var? (aria2'nin 6800'i gibi
    acik ama yanit vermeyen portlari ele — yalnizca FastAPI 422 doner.)"""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/download", data=b"x",
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
    """Sunucu yoksa exe'yi veya geliştirme ortamında run.py'yi gizli başlatır, portu döndürür."""
    port = port_bul()
    if port:
        return port

    exe = _exe_bul()
    if exe and exe.exists():
        subprocess.Popen(
            ["cmd", "/c", "start", "", "/min", str(exe), "--gizli"],
            close_fds=True)
    else:
        kok = _proje_koku()
        if kok and (kok / "run.py").is_file():
            subprocess.Popen(
                [sys.executable, str(kok / "run.py"), "--gizli"],
                close_fds=True)
        else:
            sys.exit("HATA: ai-dl-bridge.exe veya run.py bulunamadı — önce derleyin veya ortamı kurun.")

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
    ap = argparse.ArgumentParser(description="Download files via ai-dl-bridge")
    ap.add_argument("url", nargs="?", help="Download URL")
    ap.add_argument("--url", dest="url_opt", help="Download URL (flag)")
    ap.add_argument("--quality", "--kalite", default="video",
                    choices=["video", "best", "eniyi", "lowest", "endusuk", "audio", "ses"])
    ap.add_argument("--agent", "--kimlik", default="agent")
    ap.add_argument("--wait", "--bekle", action="store_true",
                    help="wait until download completes and stream progress")
    a = ap.parse_args()

    hedef_url = a.url or a.url_opt
    if not hedef_url:
        ap.error("URL is required (positional or --url)")

    port = sunucu_hazirla()
    yanit = post_json(
        f"http://127.0.0.1:{port}/download",
        {"url": hedef_url, "agent": a.agent, "quality": a.quality})
    print(json.dumps(yanit, ensure_ascii=False))

    durum = yanit.get("status") or yanit.get("durum")
    if durum in ("rejected", "reddedildi"):
        return 1
    if (a.wait or a.bekle) and yanit.get("id"):
        return bekle_gid(yanit["id"])
    print(f"Folder: {INDIRME_KLASORU}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
