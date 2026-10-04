"""Task 1-2 testleri — daemon bulma hatası + viewmodel saf mantık."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from ui.viewmodel import (boyut_format, hiz_format, kisalt, ozet,  # noqa: E402
                          satir_yap, yuzde)


def test_app_modulu_yuklenir():
    """GUI modülü import edilebilir olmalı (exe'de yakalanan hata sınıfı)."""
    import ui.app  # noqa: F401


class TestOtomatikBaslatma:
    """ui/autostart.py — gerçek registry'ye dokunmadan sahte winreg ile."""

    class _SahteAnahtar:
        def __init__(self, depo):
            self.depo = depo

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _SahteWinreg:
        HKEY_CURRENT_USER = 0
        KEY_SET_VALUE = 0
        REG_SZ = 1

        def __init__(self):
            self.depo = {}

        def OpenKey(self, hk, yol, *a, **k):
            return TestOtomatikBaslatma._SahteAnahtar(self.depo)

        def CreateKey(self, hk, yol):
            return TestOtomatikBaslatma._SahteAnahtar(self.depo)

        def QueryValueEx(self, k, ad):
            if ad not in self.depo:
                raise OSError("kayıt yok")
            return (self.depo[ad], 1)

        def SetValueEx(self, k, ad, sira, tip, deger):
            self.depo[ad] = deger

        def DeleteValue(self, k, ad):
            if ad not in self.depo:
                raise OSError("kayıt yok")
            del self.depo[ad]

    def test_ac_kapa_dongusu(self, monkeypatch):
        from ui import autostart
        sahte = self._SahteWinreg()
        monkeypatch.setattr(autostart, "_winreg", lambda: sahte)
        assert autostart.aktif_mi() is False
        autostart.etkinlestir()
        assert autostart.aktif_mi() is True
        assert "--tray" in sahte.depo[autostart.ANAHTAR_ADI]
        autostart.devre_disi_birak()
        assert autostart.aktif_mi() is False

    def test_baslatma_komutu(self, monkeypatch):
        from ui import autostart
        monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)
        komut = autostart.baslatma_komutu()
        assert komut.startswith('"') and "--tray" in komut


class TestYollar:
    """bridge/paths.py — geliştirme vs. dondurulmuş (.exe) ortam."""

    def test_gelistirmede_proje_koku(self):
        from bridge.paths import paket_koku
        kok = paket_koku()
        assert (kok / "bridge").is_dir() and (kok / "tools").is_dir()

    def test_frozenda_meipass_koku(self, monkeypatch, tmp_path):
        from bridge import paths
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        (tmp_path / "tools").mkdir()
        (tmp_path / "tools" / "aria2c.exe").write_text("sahte")
        assert paths.paket_koku() == tmp_path
        from ui.daemon import binary_bul
        with patch("ui.daemon.shutil.which", return_value=None):
            assert binary_bul() == str(tmp_path / "tools" / "aria2c.exe")


class TestViewmodel:
    def test_kisalt_orta_keser(self):
        s = kisalt("https://www.youtube.com/watch?v=abc123XYZ", 32)
        assert "…" in s and len(s) == 32 and s.startswith("https://www.you")

    def test_kisalt_kisaysa_dokunma(self):
        assert kisalt("kisa.zip", 32) == "kisa.zip"

    def test_hiz_format_siniflari(self):
        assert hiz_format(0) == "0 B/s"
        assert hiz_format(512) == "512 B/s"
        assert hiz_format(1536) == "1.5 KB/s"
        assert hiz_format(2 * 1024**2) == "2 MB/s"

    def test_boyut_format_siniflari(self):
        # 2026-10-01 regresyon: döngü sonundaki /1024 iki kez uygulanıp
        # 7516 bayt'i "0 KB" yapıyordu.
        assert boyut_format(0) == "0 B"
        assert boyut_format(512) == "512 B"
        assert boyut_format(7516) == "7.3 KB"
        assert boyut_format(1421570) == "1.4 MB"
        assert boyut_format(3 * 1024**3) == "3 GB"

    def test_yuzde_sifir_bolme(self):
        assert yuzde(5, 0) == 0
        assert yuzde(1, 4) == 25
        assert yuzde(99, 10) == 100  # taşma koruması

    def test_satir_renkleri_ve_aksiyon(self):
        aktif = satir_yap({"gid": "g1", "status": "active",
                           "totalLength": "100", "completedLength": "47",
                           "downloadSpeed": "1024",
                           "files": [{"path": "/dl/dosya.zip"}]})
        assert aktif["renk"] == "#6fbf9e" and aktif["yuzde"] == 47
        assert aktif["actions"] == ["pause", "cancel"]
        assert aktif["baslik"] == "dosya.zip"

        durak = satir_yap({"gid": "g2", "status": "paused", "files": []})
        assert durak["actions"] == ["resume", "cancel"]

        bitti = satir_yap({"gid": "g3", "status": "complete", "files": []})
        assert bitti["bitti"] and bitti["actions"] == []

        hata = satir_yap({"gid": "g4", "status": "error", "files": []})
        assert hata["renk"] == "#d98c8c"

    def test_ozet_hesabi(self):
        satirlar = [
            {"durum": "active", "kalan": 500, "bitti": False, "_hiz_bayt": 1024},
            {"durum": "active", "kalan": 500, "bitti": False, "_hiz_bayt": 2048},
            {"durum": "complete", "kalan": 0, "bitti": True},
        ]
        o = ozet(satirlar)
        assert o["aktif"] == 2 and o["toplam_hiz_bayt"] == 3072 and o["kalan_bayt"] == 1000


class TestDaemon:
    def test_binary_yoksa_aciklamali_hata(self):
        from ui.daemon import DaemonHatasi, binary_bul
        with patch("ui.daemon.Path.exists", return_value=False), \
             patch("ui.daemon.shutil.which", return_value=None), \
             pytest.raises(DaemonHatasi, match="aria2c not found"):
            binary_bul()

    def test_binary_varsa_yol_doner(self):
        from ui.daemon import binary_bul
        with patch("ui.daemon.Path.exists", return_value=False), \
             patch("ui.daemon.shutil.which", return_value="/usr/bin/aria2c"):
            assert binary_bul() == "/usr/bin/aria2c"

    def test_yerel_binary_once_gelir(self, tmp_path, monkeypatch):
        """tools/aria2c.exe varken PATH'e hiç bakılmaz."""
        from ui import daemon
        (tmp_path / "tools").mkdir(parents=True, exist_ok=True)
        sahte_yerel = tmp_path / "tools" / "aria2c.exe"
        sahte_yerel.write_text("sahte")
        monkeypatch.setattr(daemon, "paket_koku", lambda: tmp_path)
        with patch("ui.daemon.shutil.which", return_value="C:\\Windows\\System32\\aria2c.exe"):
            yol = daemon.binary_bul()
            assert yol == str(sahte_yerel)
