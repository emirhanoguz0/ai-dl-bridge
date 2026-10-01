"""Link çözümleme — yt-dlp INDIRMEZ, sadece düz link üretir (spec §2).

Video sitesi linkleri yt-dlp ile çözülür; düz dosya linkleri olduğu gibi geçer.
yt-dlp bulunamazsa/bozuksa VideoCozumHatasi yükselir — AI'a açıklamalı gider.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse


class VideoCozumHatasi(Exception):
    pass


VIDEO_ALANLARI = (
    "youtube.com", "youtu.be", "tiktok.com", "instagram.com", "twitter.com",
    "x.com", "vimeo.com", "dailymotion.com", "facebook.com", "fb.watch",
    "twitch.tv", "reddit.com",
)


@dataclass
class Cozum:
    link: str            # indirilecek düz link
    baslik: str = ""     # gösterim adı (boşsa link kullanılır)
    boyut: int | None = None  # biliniyorsa bayt
    video_mu: bool = False


def video_sitesi_mi(link: str) -> bool:
    host = urlparse(link).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in VIDEO_ALANLARI)


def _yt_dlp_yolu() -> str:
    yol = shutil.which("yt-dlp")
    if yol:
        return yol
    # gömülü binary (geliştirmede proje tools/, .exe'de çıkarma klasörü)
    from bridge.paths import paket_koku
    yerel = paket_koku() / "tools" / "yt-dlp.exe"
    if yerel.exists():
        return str(yerel)
    raise VideoCozumHatasi("yt-dlp bulunamadı — tools/yt-dlp.exe eksik")


def _tahmini_boyut(link: str) -> int | None:
    try:
        req = urllib.request.Request(link, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as r:
            uzunluk = r.headers.get("Content-Length")
            return int(uzunluk) if uzunluk else None
    except Exception:
        return None


def _yt_dlp_calistir(komut: list, link: str) -> dict:
    komut = komut + [link]
    try:
        out = subprocess.run(
            komut,
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise VideoCozumHatasi("yt-dlp zaman aşımı (120 sn) — site yanıt vermiyor")
    if out.returncode != 0:
        mesaj = (out.stderr or out.stdout).strip().splitlines()
        raise VideoCozumHatasi(f"yt-dlp çözemedi: {mesaj[-1] if mesaj else 'bilinmeyen hata'}")
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        raise VideoCozumHatasi("yt-dlp çıktısı bozuk — muhtemelen site yapısı değişti")


def coz(link: str, kalite: str = "eniyi") -> Cozum:
    """Link → indirme planı. Dosya boyutunu bilebildiğinde doldurur.

    kalite: "eniyi" (varsayılan, en iyi tek dosya akışı), "ses" (en iyi ses)
    veya "endusuk" (en küçük dosya — test/kısıtlı bağlantı için).
    """
    if not video_sitesi_mi(link):
        return Cozum(link=link, baslik=link.rsplit("/", 1)[-1] or link,
                     boyut=_tahmini_boyut(link), video_mu=False)

    yol = _yt_dlp_yolu()
    taban = [yol, "-J", "--no-playlist", "--no-warnings"]
    if kalite == "endusuk":
        # HLS (m3u8) akışlarını ele — aria2 onları dosya olarak indiremez,
        # .m3u8 oynatma listesi iner (v3 canlı testinde görüldü). Yeni YouTube
        # videolarında birleşik ilerleyen akış kalmadığı için ses en küçük
        # direkt indirilebilir dosyadır.
        secici = ("worst[protocol!*=m3u8][vcodec!=none][acodec!=none]"
                  "/worstaudio[protocol!*=m3u8][ext=m4a]"
                  "/worstaudio[protocol!*=m3u8]/worstaudio")
    elif kalite == "ses":
        secici = "bestaudio[ext=m4a]/bestaudio[protocol!*=m3u8]/bestaudio"
    else:  # eniyi
        secici = ("best[protocol!*=m3u8][vcodec!=none]"
                  "/best[protocol!*=m3u8]/best")

    bilgi = _yt_dlp_calistir(taban + ["-f", secici], link)
    url = bilgi.get("url") or (bilgi.get("requested_downloads") or [{}])[0].get("url")
    if not url:
        raise VideoCozumHatasi("video akış linki çıkarılamadı (site koruması?)")
    boyut = bilgi.get("filesize") or bilgi.get("filesize_approx") \
        or (bilgi.get("requested_downloads") or [{}])[0].get("filesize")
    return Cozum(link=url, baslik=bilgi.get("title", link),
                 boyut=boyut, video_mu=True)


@dataclass
class VideoPlan:
    """Gerçek video indirme planı — DASH dünyasında tek akış yetmez.

    Modern YouTube'da birleşik (video+ses) ilerleyen akış yok; en iyi kalite
    video-only + audio-only parçaların ffmpeg ile birleştirilmesiyle elde edilir.
    ses_url None ise tek akış yeterlidir (birleştirme gerekmez).
    """
    video_url: str
    ses_url: str | None
    baslik: str
    video_boyut: int | None
    ses_boyut: int | None
    video_uzanti: str = "mp4"
    ses_uzanti: str = "m4a"

    @property
    def toplam_boyut(self) -> int | None:
        if self.video_boyut is None and self.ses_boyut is None:
            return None
        return (self.video_boyut or 0) + (self.ses_boyut or 0)


def temiz_ad(ad: str, sinir: int = 120) -> str:
    """Windows dosya adı için güvenli hale getirir."""
    for ch in '<>:"/\\|?*':
        ad = ad.replace(ch, "_")
    ad = "".join(c for c in ad if ord(c) >= 32).strip(" .")
    return (ad or "video")[:sinir]


def coz_video(link: str) -> VideoPlan:
    """Video sitesi linki → video (+ses) parça linkleri, birleştirme planı."""
    yol = _yt_dlp_yolu()
    # önce birleşik ilerleyen akış dene (tek dosya, ffmpeg'siz), sonra DASH çifti
    secici = ("best[protocol!*=m3u8][vcodec!=none][acodec!=none]"
              "/bestvideo[ext=mp4][protocol!*=m3u8]+bestaudio[ext=m4a][protocol!*=m3u8]"
              "/bestvideo[protocol!*=m3u8]+bestaudio[protocol!*=m3u8]")
    bilgi = _yt_dlp_calistir(
        [yol, "-J", "--no-playlist", "--no-warnings", "-f", secici], link)
    # çift akış (a+b) seçiminde -J, parçaları requested_downloads yerine
    # requested_formats altında verir; tek akışta requested_downloads yeterli.
    parcalar = (bilgi.get("requested_downloads") or []) \
        + (bilgi.get("requested_formats") or [])
    baslik = bilgi.get("title", link)

    def _parca(kosul):
        return next((p for p in parcalar if p.get("url") and kosul(p)), None)

    tek = _parca(lambda p: p.get("vcodec") not in (None, "none")
                 and p.get("acodec") not in (None, "none"))
    if tek:
        return VideoPlan(video_url=tek["url"], ses_url=None, baslik=baslik,
                         video_boyut=tek.get("filesize") or tek.get("filesize_approx"),
                         ses_boyut=None,
                         video_uzanti=tek.get("ext") or "mp4")

    video = _parca(lambda p: p.get("vcodec") not in (None, "none"))
    ses = _parca(lambda p: p.get("vcodec") in (None, "none")
                 and p.get("acodec") not in (None, "none"))
    if not video:
        raise VideoCozumHatasi("video akışı çıkarılamadı (site koruması?)")
    if not ses:
        raise VideoCozumHatasi("ses akışı çıkarılamadı — birleşik video kurulamaz")
    return VideoPlan(video_url=video["url"], ses_url=ses["url"], baslik=baslik,
                     video_boyut=video.get("filesize") or video.get("filesize_approx"),
                     ses_boyut=ses.get("filesize") or ses.get("filesize_approx"),
                     video_uzanti=video.get("ext") or "mp4",
                     ses_uzanti=ses.get("ext") or "m4a")
