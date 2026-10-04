"""Windows başlangıcında otomatik başlatma (HKCU Run anahtarı).

--gizli bayrağıyla başlar: pencere açılmaz, tepside sessizce bekler.
Windows dışında tüm işlevler güvenli biçimde pas geçer.
"""
from __future__ import annotations

import sys
from pathlib import Path

ANAHTAR_ADI = "ai-dl-bridge"
RUN_YOLU = r"Software\Microsoft\Windows\CurrentVersion\Run"


def baslatma_komutu() -> str:
    """Run key command line."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    run_py = Path(__file__).resolve().parent.parent / "run.py"
    return f'"{sys.executable}" "{run_py}" --tray'


def _winreg():
    if sys.platform != "win32":
        return None
    try:
        import winreg
        return winreg
    except ImportError:
        return None


def aktif_mi() -> bool:
    """Başlangıçta başlatma kayıtlı mı?"""
    winreg = _winreg()
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_YOLU) as k:
            winreg.QueryValueEx(k, ANAHTAR_ADI)
        return True
    except OSError:
        return False


def etkinlestir() -> None:
    """Başlangıçta --gizli olarak başlat."""
    winreg = _winreg()
    if winreg is None:
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_YOLU) as k:
        winreg.SetValueEx(k, ANAHTAR_ADI, 0, winreg.REG_SZ,
                          baslatma_komutu())


def devre_disi_birak() -> None:
    """Başlangıç kaydını sil."""
    winreg = _winreg()
    if winreg is None:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_YOLU,
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, ANAHTAR_ADI)
    except OSError:
        pass  # kayıt zaten yok
