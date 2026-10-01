"""Saf mantık — GUI'siz test edilir. aria2 durum dict'i → görünüm modeli."""
from __future__ import annotations

RENKLER = {"active": "#6fbf9e", "paused": "#e8b06e",
           "error": "#d98c8c", "complete": "#a8a3b8", "waiting": "#7ea8d8"}


def kisalt(link: str, uzunluk: int = 32) -> str:
    """youtube.com/…xyz123 — ortadan keser."""
    if len(link) <= uzunluk:
        return link
    sol = (uzunluk - 1) // 2
    sag = uzunluk - sol - 1
    return link[:sol] + "…" + link[-sag:]


def hiz_format(bayt_sn) -> str:
    if bayt_sn <= 0:
        return "0 B/s"
    deger = float(bayt_sn)
    for birim in ("B/s", "KB/s", "MB/s", "GB/s"):
        if deger < 1024 or birim == "GB/s":
            metin = f"{deger:.0f}" if deger == int(deger) else f"{deger:.1f}"
            return f"{metin} {birim}"
        deger /= 1024


def boyut_format(bayt: int) -> str:
    deger = float(bayt)
    for birim in ("B", "KB", "MB", "GB"):
        if deger < 1024 or birim == "GB":
            metin = f"{deger:.0f}" if deger == int(deger) else f"{deger:.1f}"
            return f"{metin} {birim}"
        deger /= 1024


def yuzde(tamamlanan: int, toplam: int) -> int:
    """0 bölme güvenli (plan Review Focus #2)."""
    if not toplam:
        return 0
    return min(100, round(100 * tamamlanan / toplam))


def satir_yap(durum: dict) -> dict:
    """aria2 tellStatus çıktısı → satır modeli."""
    durum_kodu = durum.get("status", "error")
    tam = int(durum.get("completedLength", 0))
    top = int(durum.get("totalLength", 0))
    hiz = int(durum.get("downloadSpeed", 0))
    dosya = (durum.get("files") or [{}])[0]
    ad = (dosya.get("path") or "").rsplit("/", 1)[-1] or durum.get("gid", "?")
    biten = durum_kodu == "complete"
    return {
        "gid": durum.get("gid"),
        "baslik": ad,
        "yuzde": yuzde(tam, top),
        "hiz": hiz_format(hiz),
        "durum": durum_kodu,
        "renk": RENKLER.get(durum_kodu, RENKLER["error"]),
        "bitti": biten,
        "kalan": max(0, top - tam),
        "aksiyonlar": [] if biten else
                      (["devam", "iptal"] if durum_kodu == "paused"
                       else ["durdur", "iptal"]),
        "_hiz_bayt": hiz,
    }


def ozet(satirlar: list[dict]) -> dict:
    aktif = [s for s in satirlar if s["durum"] == "active"]
    hizler = [int(s.get("_hiz_bayt", 0)) for s in aktif]
    kalan = sum(s.get("kalan", 0) for s in satirlar if not s.get("bitti"))
    return {
        "aktif": len(aktif),
        "bekleyen": sum(1 for s in satirlar if s["durum"] == "waiting"),
        "toplam_hiz_bayt": sum(hizler),
        "kalan_bayt": kalan,
    }
