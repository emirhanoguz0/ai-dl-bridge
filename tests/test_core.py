"""Birim testler — internetsiz çalışır (sahte aria2 / sahte yt-dlp)."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.policy import ONAY_LIMITI, degerlendir           # noqa: E402
from bridge.resolver import Cozum, coz, video_sitesi_mi      # noqa: E402
from bridge.server import bos_port_bul, uygulama_yarat       # noqa: E402
from bridge.aria2_rpc import Aria2RPC                        # noqa: E402


class TestPolicy:
    def test_kucuk_dosya_aninda(self):
        k = degerlendir(1024**3)
        assert k.uygun and not k.beklemede

    def test_iki_gb_ustu_beklemede(self):
        k = degerlendir(ONAY_LIMITI + 1)
        assert k.beklemede and ("approval" in k.sebep.lower() or "onay" in k.sebep.lower())

    def test_boyut_bilinmiyorsa_guvenli_taraf(self):
        k = degerlendir(None)
        assert k.uygun


class TestVideoTespit:
    @pytest.mark.parametrize("link", [
        "https://www.youtube.com/watch?v=x", "https://youtu.be/x",
        "https://www.tiktok.com/@k/video/1", "https://x.com/a/status/1",
    ])
    def test_video_siteleri(self, link):
        assert video_sitesi_mi(link)

    @pytest.mark.parametrize("link", [
        "https://physionet.org/files/x.zip", "https://example.com/dosya.pdf",
    ])
    def test_normal_dosya(self, link):
        assert not video_sitesi_mi(link)

    def test_duz_link_oldugu_gibi_gecer(self):
        with patch("bridge.resolver._tahmini_boyut", return_value=123):
            c = coz("https://example.com/rapor.pdf")
        assert c.link.endswith("rapor.pdf") and not c.video_mu and c.boyut == 123

    def test_yt_dlp_bozuksa_aciklamali_hata(self):
        from bridge.resolver import VideoCozumHatasi
        yanlis = type("R", (), {"returncode": 1, "stdout": "", "stderr": "ERROR: site kapali"})()
        with patch("bridge.resolver.video_sitesi_mi", return_value=True), \
             patch("bridge.resolver._yt_dlp_yolu", return_value="yt-dlp"), \
             patch("subprocess.run", return_value=yanlis), \
             pytest.raises(VideoCozumHatasi, match="site kapali"):
            coz("https://youtu.be/x")

    def test_endusuk_kalite_format_argumanu_ekler(self):
        """kalite='endusuk' yt-dlp komutuna -f worst ekler (canlı test isteği)."""
        yanlis = type("R", (), {"returncode": 1, "stdout": "", "stderr": "yok"})()
        with patch("bridge.resolver.video_sitesi_mi", return_value=True), \
             patch("bridge.resolver._yt_dlp_yolu", return_value="yt-dlp"), \
             patch("subprocess.run", return_value=yanlis) as calisti, \
             pytest.raises(Exception):
            coz("https://youtu.be/x", kalite="endusuk")
        komut = calisti.call_args[0][0]
        assert "-f" in komut and any("worst" in a for a in komut)

    def test_ses_kalite_bestaudio_argumanu_ekler(self):
        """kalite='ses' en iyi ses akışını seçer (şarkılar için)."""
        yanlis = type("R", (), {"returncode": 1, "stdout": "", "stderr": "yok"})()
        with patch("bridge.resolver.video_sitesi_mi", return_value=True), \
             patch("bridge.resolver._yt_dlp_yolu", return_value="yt-dlp"), \
             patch("subprocess.run", return_value=yanlis) as calisti, \
             pytest.raises(Exception):
            coz("https://youtu.be/x", kalite="ses")
        komut = calisti.call_args[0][0]
        assert "-f" in komut and any("bestaudio" in a for a in komut)


class TestPortBulma:
    def test_dolu_port_atlanir(self):
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        dolu = s.getsockname()[1]
        bulunan = bos_port_bul(dolu)
        assert bulunan > dolu
        s.close()


class TestRPCKonusma:
    def _yanit(self, result):
        class R:
            def read(self):
                return json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        return R()

    def test_add_uri(self):
        rpc = Aria2RPC(port=6800)
        with patch("urllib.request.urlopen", return_value=self._yanit("gid123")):
            gid = rpc.add_uri("http://x/d.zip", "C:/dl")
        assert gid == "gid123"

    def test_tell_stopped_kucuk_dosya_racei(self):
        """Saniyeden hizli inen dosyalar icin stopped listesi sorgulanir."""
        import json as _json
        rpc = Aria2RPC(port=6800)
        yakalanan = {}

        class R:
            def read(self):
                return _json.dumps({"jsonrpc": "2.0", "id": 1, "result": []}).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def sahte_urlopen(req, timeout=10):
            yakalanan["yontem"] = _json.loads(req.data)["method"]
            return R()

        with patch("urllib.request.urlopen", side_effect=sahte_urlopen):
            rpc.tell_stopped(0, 50)
        assert yakalanan["yontem"] == "aria2.tellStopped"

    def test_hata_ayiklanir(self):
        class HataR:
            def read(self):
                return json.dumps({"jsonrpc": "2.0", "id": 1,
                                   "error": {"code": 1, "message": "bozuk"}}).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        rpc = Aria2RPC()
        from bridge.aria2_rpc import Aria2Error
        with patch("urllib.request.urlopen", return_value=HataR()), \
             pytest.raises(Aria2Error, match="bozuk"):
            rpc.tell_status("x")


class TestSunucu:
    class _SahteRPC:
        def __init__(self):
            self.cagrilar = []

        def add_uri(self, link, out_dir, out_name=None, paused=False):
            self.cagrilar.append((link, paused))
            return "gid-sahte"

    def _client(self, rpc):
        from fastapi.testclient import TestClient
        return TestClient(uygulama_yarat(rpc))

    def test_reddedildi_yolu(self):
        from bridge.resolver import VideoCozumHatasi
        client = self._client(self._SahteRPC())
        with patch("bridge.server.coz", side_effect=VideoCozumHatasi("link dead")), \
             patch("bridge.server.coz_video",
                   side_effect=VideoCozumHatasi("video dead")):
            # English endpoint and payload
            r = client.post("/download", json={"url": "https://youtu.be/x", "agent": "kimi"})
            assert r.json()["status"] == "rejected" and "dead" in r.json()["reason"]
            assert r.json()["durum"] == "reddedildi"
            # Legacy endpoint and payload
            r_legacy = client.post("/indir", json={"link": "https://youtu.be/x", "kimlik": "kimi"})
            assert r_legacy.json()["durum"] == "reddedildi"

    def test_kabul_yolu(self):
        rpc = self._SahteRPC()
        client = self._client(rpc)
        with patch("bridge.server.coz",
                   return_value=Cozum(link="http://x/f.zip", boyut=100)):
            # English endpoint and payload
            r = client.post("/download", json={"url": "http://x/f.zip", "agent": "kimi"})
            assert r.json()["status"] == "accepted" and r.json()["id"] == "gid-sahte"
            assert r.json()["durum"] == "kabul"
            # Legacy endpoint
            r_legacy = client.post("/indir", json={"link": "http://x/f.zip", "kimlik": "kimi"})
            assert r_legacy.json()["durum"] == "kabul"
        assert rpc.cagrilar == [("http://x/f.zip", False), ("http://x/f.zip", False)]

    def test_beklemede_yolu(self):
        rpc = self._SahteRPC()
        client = self._client(rpc)
        with patch("bridge.server.coz",
                   return_value=Cozum(link="http://x/b.zip", boyut=10 * 1024**3)):
            r = client.post("/download", json={"url": "http://x/b.zip", "agent": "kimi"})
            assert r.json()["status"] == "pending" and r.json()["durum"] == "beklemede"
        assert rpc.cagrilar == [("http://x/b.zip", True)]  # paused=True in queue
