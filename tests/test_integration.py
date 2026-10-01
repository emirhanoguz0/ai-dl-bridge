"""Bütünleşik test — gerçek aria2c + yerel dosya sunucusu.

tools/aria2c.exe yoksa atlanır (CI'da koşulmasın diye değil, makinede
kurulum yoksa testleri kırmamak için).
"""
import http.server
import re
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

aria2c = pytest.importorskip("shutil").which("aria2c") or \
    (Path(__file__).parent.parent / "tools" / "aria2c.exe")
if not Path(str(aria2c)).exists():
    pytest.skip("aria2c yok — tools/aria2c.exe koyun", allow_module_level=True)

from ui.daemon import Aria2Daemon  # noqa: E402
from bridge.aria2_rpc import Aria2RPC  # noqa: E402

RPC_PORT = 6990
HTTP_PORT = 6991
DOSYA_BOYUT = 4 * 1024 * 1024  # 4 MB


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler'a HTTP Range desteği ekler.

    aria2 parçalı indirme için Range ister; desteklenmezse
    'Invalid range header' hatasıyla indirme error olur.
    """

    def log_message(self, *a):
        pass

    def do_GET(self):
        import os
        yol = self.translate_path(self.path)
        if not os.path.isfile(yol):
            return super().do_GET()
        boyut = os.path.getsize(yol)
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if m and (m.group(1) or m.group(2)):
            bas = int(m.group(1) or 0)
            bit = min(int(m.group(2) or boyut - 1), boyut - 1)
            if bas > bit:
                self.send_error(416)
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {bas}-{bit}/{boyut}")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(bit - bas + 1))
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            kalan = bit - bas + 1
            with open(yol, "rb") as f:
                f.seek(bas)
                while kalan > 0:
                    parca = f.read(min(65536, kalan))
                    if not parca:
                        break
                    self.wfile.write(parca)
                    kalan -= len(parca)
        else:
            self.send_response(200)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(boyut))
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            with open(yol, "rb") as f:
                shutil.copyfileobj(f, self.wfile)


@pytest.fixture(scope="module")
def aria2():
    daemon = Aria2Daemon(port=RPC_PORT)
    daemon.start()
    yield daemon
    daemon.stop()


@pytest.fixture(scope="module")
def dosya_sunucusu(tmp_path_factory):
    """Yerel HTTP sunucusu — rastgele 4 MB dosya sunar."""
    klasor = tmp_path_factory.mktemp("sunucu")
    icerik = b"\xab" * DOSYA_BOYUT
    (klasor / "buyuk.bin").write_bytes(icerik)

    sunucu = http.server.ThreadingHTTPServer(
        ("127.0.0.1", HTTP_PORT),
        lambda *a, **k: RangeHandler(*a, directory=str(klasor), **k))
    thread = threading.Thread(target=sunucu.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{HTTP_PORT}/buyuk.bin"
    sunucu.shutdown()


def _bekle(rpc, gid, durumlar, zaman_asimi=15):
    """gid beklenen durumlardan birine ulaşana dek bekle."""
    son = time.time() + zaman_asimi
    while time.time() < son:
        try:
            s = rpc.tell_status(gid)
        except Exception:
            s = {}
        if s.get("status") in durumlar:
            return s
        time.sleep(0.1)
    raise AssertionError(f"{gid} durumu {durumlar} olmadı (son: {s.get('status')})")


def test_indir_duraklat_devam_iptal(aria2, dosya_sunucusu, tmp_path):
    rpc = Aria2RPC(port=RPC_PORT)
    # Dosya localhost'ta ışık hızında iner; hız/ilerleme doğrulaması için
    # indirmeyi bilinçli yavaşlat (~8 sn sürer).
    rpc.set_speed_limit(512 * 1024)
    try:
        gid = rpc.add_uri(dosya_sunucusu, str(tmp_path))

        # 1) İniyor ve ilerliyor mu? (anlamlı miktarda bayt düşene dek bekle)
        _bekle(rpc, gid, ["active"])
        son = time.time() + 10
        s = rpc.tell_status(gid)
        while int(s["completedLength"]) < 64 * 1024 and time.time() < son:
            time.sleep(0.1)
            s = rpc.tell_status(gid)
        tam = int(s["completedLength"])
        assert tam >= 64 * 1024, "indirme ilerlemiyor"
        assert int(s["downloadSpeed"]) > 0, "hız sıfır göründü"
        yuzde = round(100 * tam / int(s["totalLength"]))
        assert 0 < yuzde < 100

        # 2) Durdur → ilerleme donmalı
        rpc.pause(gid)
        _bekle(rpc, gid, ["paused"])
        time.sleep(0.4)
        a = int(rpc.tell_status(gid)["completedLength"])
        time.sleep(0.3)
        b = int(rpc.tell_status(gid)["completedLength"])
        assert a == b, "durduruldu ama ilerliyor"

        # 3) Devam → bitene dek
        rpc.unpause(gid)
        s = _bekle(rpc, gid, ["complete"], zaman_asimi=30)
        assert int(s["completedLength"]) == DOSYA_BOYUT
    finally:
        rpc.set_speed_limit(0)

    indi = tmp_path / "buyuk.bin"
    assert indi.read_bytes() == b"\xab" * DOSYA_BOYUT

    # 4) İptal akışı: yeni indirme başlat, duraklat, kuyruktan kaldır
    gid2 = rpc.add_uri(dosya_sunucusu, str(tmp_path), out_name="ikinci.bin")
    _bekle(rpc, gid2, ["active"])
    rpc.pause(gid2)
    _bekle(rpc, gid2, ["paused"])
    rpc.remove(gid2)
    with pytest.raises(Exception):
        rpc.tell_status(gid2)


def test_hiz_limiti(aria2):
    rpc = Aria2RPC(port=RPC_PORT)
    rpc.set_speed_limit(1024 * 1024)   # 1 MB/s
    rpc.set_speed_limit(0)             # geri aç
