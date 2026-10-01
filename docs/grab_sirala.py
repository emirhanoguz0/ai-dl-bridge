"""Kolon basligi tiklamasi dogrulamasi: Boyut'a tikla, yeni sirayi yakala."""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication

from bridge.aria2_rpc import Aria2RPC
from ui.app import Pencere

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(True)
p = Pencere(rpc=Aria2RPC(), sunucu_portu=8765)
p.show()
time.sleep(2.5)
app.processEvents()

p.kolon_boyut._tikla()   # boyuta gore sirala (büyük önce)
time.sleep(0.5)
app.processEvents()
p.grab().save(str(Path(__file__).parent / "ekran-v4-sirala-boyut.png"))

p.kolon_boyut._tikla()   # yön değiştir (küçük önce)
time.sleep(0.5)
app.processEvents()
p.grab().save(str(Path(__file__).parent / "ekran-v4-sirala-boyut-ters.png"))
print("kolon:", p._siralama_kolon, "| ters:", p._siralama_ters)
