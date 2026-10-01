"""v3 ekran görüntüsü: gerçek daemon + sahte 3 satır + paused seçili."""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ui.daemon import Aria2Daemon
from ui.app import Pencere
from ui import viewmodel

daemon = Aria2Daemon()
daemon.start()

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(True)
p = Pencere(rpc=daemon.rpc, sunucu_portu=8765)
p.show()

RENK = viewmodel.RENKLER
satirlar = [
    {"gid": "aaa1", "baslik": "BIDSleep-dataset-1.0.0.zip", "yuzde": 47,
     "hiz": "12.4 MB/s", "durum": "active", "renk": RENK["active"],
     "bitti": False, "kalan": 10**9, "aksiyonlar": [], "_hiz_bayt": 13_000_000},
    {"gid": "bbb2", "baslik": "sleep-accel-forecasting.zip", "yuzde": 12,
     "hiz": "duraklatıldı", "durum": "paused", "renk": RENK["paused"],
     "bitti": False, "kalan": 5 * 10**8, "aksiyonlar": [], "_hiz_bayt": 0},
    {"gid": "ccc3", "baslik": "pima-indians-diabetes.csv", "yuzde": 100,
     "hiz": "tamamlandı", "durum": "complete", "renk": RENK["complete"],
     "bitti": True, "kalan": 0, "aksiyonlar": [], "_hiz_bayt": 0},
]
p._gid_durum = {s["gid"]: s["durum"] for s in satirlar}
p._listeyi_doldur(satirlar)

# paused satırını seç (buton durumları görünsün)
for i in range(p.liste.count()):
    if p.liste.item(i).data(Qt.ItemDataRole.UserRole) == "bbb2":
        p.liste.setCurrentRow(i)
        break

p.ozet_etiket.setText("1 indiyor · 1 bekliyor · 12.4 MB/s · kalan 1.5 GB")
app.processEvents()
time.sleep(0.4)
p.grab().save(str(Path(__file__).parent / "ekran-v3.png"))
print("butonlar: devam=%s durdur=%s sil=%s" % (
    p.devam_dugme.isEnabled(), p.durdur_dugme.isEnabled(),
    p.sil_dugme.isEnabled()))

daemon.stop()
