"""Çalıştırma ortamına göre paket kökünü çözer.

Geliştirmede: proje kökü (bridge/ ve ui/ arasındaki dizin).
PyInstaller .exe'de: binary'lerin gömülü olduğu geçici çıkarma klasörü
(sys._MEIPASS). Böylece tools/aria2c.exe ve tools/yt-dlp.exe iki ortamda
da bulunur.
"""
from __future__ import annotations

import sys
from pathlib import Path


def paket_koku() -> Path:
    """tools/ klasörünün bulunduğu kök dizin."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def indirme_koku() -> Path:
    """Varsayılan indirme klasörü: uygulamanın İÇİNDEKİ downloads/.

    Paket çıkarma klasörüne (sys._MEIPASS) DEĞİL, kalıcı uygulama konumuna
    yazar: exe'de exe'nin yanı, geliştirmede proje kökü. Böylece indirilen
    dosyalar her zaman uygulamanın kendi alanında kalır.
    """
    if getattr(sys, "frozen", False):
        kok = Path(sys.executable).parent
    else:
        kok = Path(__file__).resolve().parent.parent
    return kok / "downloads"
