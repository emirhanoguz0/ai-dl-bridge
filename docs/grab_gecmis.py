"""Kalici gecmis dogrulamasi: mevcut aria2'ye baglan, pencereyi ac, yakala."""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from bridge.aria2_rpc import Aria2RPC
from ui.app import Pencere

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(True)
p = Pencere(rpc=Aria2RPC(), sunucu_portu=8765)  # yeni daemon YOK: gercek aria2'ye bakar
p.show()
time.sleep(2.5)   # yenile() gecmisi diskten yuklesin
app.processEvents()
p.grab().save(str(Path(__file__).parent / "ekran-v4-gecmis.png"))
print("satir sayisi:", p.liste.count())
