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
    # embedded binary (tools/ in project dev, extraction folder in .exe)
    from bridge.paths import paket_koku
    yerel = paket_koku() / "tools" / "yt-dlp.exe"
    if yerel.exists():
        return str(yerel)
    raise VideoCozumHatasi("yt-dlp not found — tools/yt-dlp.exe missing")


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
        raise VideoCozumHatasi("yt-dlp timeout (120s) — site not responding")
    if out.returncode != 0:
        mesaj = (out.stderr or out.stdout).strip().splitlines()
        raise VideoCozumHatasi(f"yt-dlp failed to resolve: {mesaj[-1] if mesaj else 'unknown error'}")
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        raise VideoCozumHatasi("yt-dlp output corrupted — site structure may have changed")


def coz(link: str, kalite: str = "best") -> Cozum:
    """Link → download plan. Populates file size when available.

    kalite / quality: "best" / "eniyi" (default, best single-file stream),
    "audio" / "ses" (best audio),
    or "lowest" / "endusuk" (smallest direct stream).
    """
    if not video_sitesi_mi(link):
        return Cozum(link=link, baslik=link.rsplit("/", 1)[-1] or link,
                     boyut=_tahmini_boyut(link), video_mu=False)

    yol = _yt_dlp_yolu()
    taban = [yol, "-J", "--no-playlist", "--no-warnings"]
    if kalite in ("endusuk", "lowest"):
        # Filter out HLS (m3u8) streams — aria2 cannot download them as files
        secici = ("worst[protocol!*=m3u8][vcodec!=none][acodec!=none]"
                  "/worstaudio[protocol!*=m3u8][ext=m4a]"
                  "/worstaudio[protocol!*=m3u8]/worstaudio")
    elif kalite in ("ses", "audio"):
        secici = "bestaudio[ext=m4a]/bestaudio[protocol!*=m3u8]/bestaudio"
    else:  # best / eniyi
        secici = ("best[protocol!*=m3u8][vcodec!=none]"
                  "/best[protocol!*=m3u8]/best")

    bilgi = _yt_dlp_calistir(taban + ["-f", secici], link)
    url = bilgi.get("url") or (bilgi.get("requested_downloads") or [{}])[0].get("url")
    if not url:
        raise VideoCozumHatasi("video stream link could not be extracted (site protection?)")
    boyut = bilgi.get("filesize") or bilgi.get("filesize_approx") \
        or (bilgi.get("requested_downloads") or [{}])[0].get("filesize")
    return Cozum(link=url, baslik=bilgi.get("title", link),
                 boyut=boyut, video_mu=True)


@dataclass
class VideoPlan:
    """Real video download plan — single stream is insufficient in DASH era.

    Modern YouTube has no combined 1080p+ stream; highest quality requires
    video-only + audio-only streams muxed with ffmpeg.
    If ses_url is None, single combined stream is used (no muxing needed).
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
    """Sanitize filename for Windows filesystem."""
    for ch in '<>:"/\\|?*':
        ad = ad.replace(ch, "_")
    ad = "".join(c for c in ad if ord(c) >= 32).strip(" .")
    return (ad or "video")[:sinir]


def coz_video(link: str) -> VideoPlan:
    """Video link → video (+ audio) stream URLs and muxing plan."""
    yol = _yt_dlp_yolu()
    secici = ("best[protocol!*=m3u8][vcodec!=none][acodec!=none]"
              "/bestvideo[ext=mp4][protocol!*=m3u8]+bestaudio[ext=m4a][protocol!*=m3u8]"
              "/bestvideo[protocol!*=m3u8]+bestaudio[protocol!*=m3u8]")
    bilgi = _yt_dlp_calistir(
        [yol, "-J", "--no-playlist", "--no-warnings", "-f", secici], link)
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
        raise VideoCozumHatasi("video stream could not be extracted (site protection?)")
    if not ses:
        raise VideoCozumHatasi("audio stream could not be extracted — cannot mux video")
    return VideoPlan(video_url=video["url"], ses_url=ses["url"], baslik=baslik,
                     video_boyut=video.get("filesize") or video.get("filesize_approx"),
                     ses_boyut=ses.get("filesize") or ses.get("filesize_approx"),
                     video_uzanti=video.get("ext") or "mp4",
                     ses_uzanti=ses.get("ext") or "m4a")
