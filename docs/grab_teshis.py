"""Buton teşhisi: ikonlar geçerli mi, disabled hali neden görünmüyor."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PyQt6.QtWidgets import QApplication, QStyle, QToolButton, QVBoxLayout, QWidget
from PyQt6.QtCore import QSize, Qt

app = QApplication(sys.argv)
stil = app.style()
w = QWidget()
lay = QVBoxLayout(w)
for ad, pm in [("play", QStyle.StandardPixmap.SP_MediaPlay),
               ("pause", QStyle.StandardPixmap.SP_MediaPause),
               ("discard", QStyle.StandardPixmap.SP_DialogDiscardButton)]:
    ikon = stil.standardIcon(pm)
    print(ad, "isNull:", ikon.isNull(), "sizes:", [str(s) for s in ikon.availableSizes()])
    aktif = QToolButton(); aktif.setIcon(ikon); aktif.setText(ad)
    aktif.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    aktif.setIconSize(QSize(20, 20)); aktif.setFixedSize(72, 50)
    pasif = QToolButton(); pasif.setIcon(ikon); pasif.setText(ad)
    pasif.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    pasif.setIconSize(QSize(20, 20)); pasif.setFixedSize(72, 50)
    pasif.setEnabled(False)
    lay.addWidget(aktif); lay.addWidget(pasif)
w.setStyleSheet(open("ui/app.py", encoding="utf-8").read().split('TEM_STILI = f"""')[1].split('"""')[0]
                .replace("{ZEMIN}", "#faf6f0").replace("{KART}", "#ffffff")
                .replace("{CIZGI}", "#e9e2d6").replace("{METIN}", "#57505e")
                .replace("{IKINCI}", "#a39dae"))
w.show()
w.grab().save(str(Path(__file__).parent / "buton-teshis.png"))
