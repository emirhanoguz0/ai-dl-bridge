"""ai-dl-bridge başlatıcı: aria2 daemon → FastAPI sunucusu (thread) → PyQt6 pencere.

Kullanım:
    python run.py            pencereyle başlar
    python run.py --gizli    pencere olmadan, tepside sessizce başlar
                             (Windows başlangıç kaydı bu kiple çalışır)
"""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

import uvicorn

from bridge.aria2_rpc import Aria2RPC
from bridge.server import bos_port_bul, uygulama_yarat


def _sunucu_baslat(rpc: Aria2RPC) -> int:
    """Tek Kapı sunucusunu arka plan thread'inde çalıştır, seçilen portu döndür."""
    port = bos_port_bul()
    uygulama = uygulama_yarat(rpc)

    def _calistir() -> None:
        try:
            uvicorn.run(uygulama, host="127.0.0.1", port=port, log_level="warning")
        except Exception:
            # GUI exe'de konsol yok; sessiz ölüm yerine kalıcı iz bırak
            import tempfile
            import traceback
            from pathlib import Path as _P
            try:
                with open(_P(tempfile.gettempdir()) / "ai-dl-bridge-sunucu-hata.log",
                          "a", encoding="utf-8") as f:
                    f.write(f"--- port {port} ---\n{traceback.format_exc()}\n")
            except OSError:
                pass

    threading.Thread(target=_calistir, daemon=True).start()
    return port


def _tek_ornek_kilit():
    """İkinci örneğin sessizce çıkmasını sağlayan kilit (QSharedMemory)."""
    from PyQt6.QtCore import QSharedMemory
    kilit = QSharedMemory("ai-dl-bridge-kilit")
    if not kilit.create(1):
        return None
    return kilit  # main() yaşamı boyunca tutulmalı


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ai-dl-bridge")
    parser.add_argument("--tray", "--silent", "--gizli", dest="tray", action="store_true",
                        help="start minimized to system tray")
    args = parser.parse_args(argv)

    from ui.daemon import Aria2Daemon, DaemonHatasi

    daemon = Aria2Daemon()
    try:
        daemon.start()
    except DaemonHatasi as e:
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            qa = QApplication(sys.argv)
            QMessageBox.critical(None, "ai-dl-bridge", f"Failed to start:\n\n{e}")
        except ImportError:
            print(f"Failed to start: {e}", file=sys.stderr)
        return 1

    sunucu_port = _sunucu_baslat(daemon.rpc)

    from PyQt6.QtWidgets import QApplication
    from bridge import server as sunucu_modul

    app = QApplication(sys.argv)
    app.setApplicationName("ai-dl-bridge")
    app.setQuitOnLastWindowClosed(False)  # do not exit on close when minimized to tray

    from ui.app import logo_ikonu
    app.setWindowIcon(logo_ikonu())

    kilit = _tek_ornek_kilit()
    if kilit is None:
        return 0  # another instance is already running

    def klasor_secildi(yeni: str) -> None:
        sunucu_modul.klasoru_degistir(Path(yeni))

    from ui.app import Pencere
    pencere = Pencere(rpc=daemon.rpc, sunucu_portu=sunucu_port,
                      indirme_klasoru=sunucu_modul.INDIRME_KLASORU,
                      klasor_secildi=klasor_secildi)
    if not args.tray:
        pencere.show()
    kod = app.exec()
    daemon.stop()
    return kod


if __name__ == "__main__":
    sys.exit(main())
