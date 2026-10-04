"""Video indirme + birleştirme birim testleri — ağ çağrıları mock'lu."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge import muxer, birlestirici  # noqa: E402
from bridge.resolver import (VideoCozumHatasi, VideoPlan, coz_video,  # noqa: E402
                             temiz_ad)
from ui.viewmodel import satir_yap  # noqa: E402


class TestTemizAd:
    def test_gecersiz_karakterler(self):
        assert temiz_ad('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j"

    def test_uzun_ad_kisalir(self):
        assert len(temiz_ad("x" * 200)) == 120

    def test_bos_ad(self):
        assert temiz_ad("   ") == "video"


def _mock_ytdlp(monkeypatch, parcalar, baslik="Test Video"):
    def sahte(komut, link):
        return {"title": baslik, "requested_downloads": parcalar}
    monkeypatch.setattr("bridge.resolver._yt_dlp_yolu", lambda: "yt-dlp")
    monkeypatch.setattr("bridge.resolver._yt_dlp_calistir", sahte)


class TestCozVideo:
    def test_birlesik_akis_tek_parca(self, monkeypatch):
        _mock_ytdlp(monkeypatch, [{"url": "http://x/v.mp4", "vcodec": "avc1",
                                   "acodec": "mp4a", "ext": "mp4",
                                   "filesize": 100}])
        plan = coz_video("https://youtu.be/abc")
        assert plan.ses_url is None and plan.video_url.endswith("v.mp4")
        assert plan.toplam_boyut == 100

    def test_dash_cifti(self, monkeypatch):
        _mock_ytdlp(monkeypatch, [
            {"url": "http://x/v.mp4", "vcodec": "avc1", "acodec": "none",
             "ext": "mp4", "filesize": 1000},
            {"url": "http://x/a.m4a", "vcodec": "none", "acodec": "mp4a",
             "ext": "m4a", "filesize": 100},
        ])
        plan = coz_video("https://youtu.be/abc")
        assert plan.ses_url == "http://x/a.m4a"
        assert plan.toplam_boyut == 1100
        assert plan.video_uzanti == "mp4" and plan.ses_uzanti == "m4a"

    def test_ses_akisi_yoksa_hata(self, monkeypatch):
        _mock_ytdlp(monkeypatch, [
            {"url": "http://x/v.mp4", "vcodec": "avc1", "acodec": "none",
             "ext": "mp4"},
        ])
        with pytest.raises(VideoCozumHatasi):
            coz_video("https://youtu.be/abc")


class TestMuxer:
    def _job(self, tmp_path, sesli=True):
        video = tmp_path / "v [part1].mp4"
        video.write_bytes(b"12345")
        ses = tmp_path / "a [part2].m4a"
        if sesli:
            ses.write_bytes(b"abc")
        return {"anahtar": "g1-1", "video_gid": "g1", "ses_gid": "g2" if sesli else None,
                "video_yol": str(video), "ses_yol": str(ses) if sesli else None,
                "hedef": str(tmp_path / "final.mp4"), "baslik": "final",
                "boyut": 8, "deneme": 0}

    def test_parcalar_eksiksizse_tamam(self, tmp_path):
        assert muxer._is_tamamlandi(self._job(tmp_path))
        assert birlestirici._is_tamamlandi(self._job(tmp_path))

    def test_aria2_artigi_varsa_bekle(self, tmp_path):
        job = self._job(tmp_path)
        Path(job["video_yol"] + ".aria2").write_text("")
        assert not muxer._is_tamamlandi(job)

    def test_tek_parca_birlesim_tasima(self, tmp_path, monkeypatch):
        job = self._job(tmp_path, sesli=False)
        monkeypatch.setattr(muxer, "isleri_oku", lambda: [job])
        monkeypatch.setattr(muxer, "_yaz", lambda x: None)

        class _SoyRpc:
            def remove_download_result(self, gid):
                return "ok"
        sonuc = muxer.bekleyenleri_isle(rpc=_SoyRpc())
        assert sonuc[0][1] in ("done", "tamam")
        assert not Path(job["video_yol"]).exists()  # part moved to destination

    def test_parca_gidleri_kumesi(self, tmp_path, monkeypatch):
        job = self._job(tmp_path)
        monkeypatch.setattr(muxer, "isleri_oku", lambda: [job])
        assert muxer.parca_gidleri() == {"g1", "g2"}


class TestSatirTamAd:
    def test_baslik_kisaltilmaz(self):
        uzun = "Dua Lipa - Training Season (Official Music Video).mp4"
        s = satir_yap({"gid": "g", "status": "complete",
                       "files": [{"path": f"/dl/{uzun}"}]})
        assert s["baslik"] == uzun
