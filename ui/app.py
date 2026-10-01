"""PyQt6 mini pencere — IDM tarzi ust arac cubugu, pastel acik tema.

Satir secilir; ustteki Resume / Pause / Remove / Folder dugmeleri ve hiz kutusu
secime/duruma uygulanir. Tamamlanan indirmeler oturum boyunca listede kalir ve
%APPDATA%/ai-dl-bridge/gecmis.json'a yazilarak oturumlar arasi korunur;
satirlarda kucuk boyut + tarih damgasi gosterilir. Listenin icindeki kolon
basliklarina (Name / Size / Date) tiklayinca tamamlananlar o kolona gore
siralir; ayni basliga tekrar tiklayinca yon degisir. Video kalitesinde parcalar
ffmpeg ile birlestirilince tek satir olarak gecmise duser. Cift tik veya
Folder dugmesi: dosyanin klasorunu acar.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QIcon, QPixmap
from PyQt6.QtWidgets import (QApplication, QComboBox, QFileDialog, QHBoxLayout,
                             QInputDialog, QLabel, QListWidget, QListWidgetItem,
                             QMenu, QMessageBox, QProgressBar, QStyle,
                             QSystemTrayIcon, QToolButton, QVBoxLayout, QWidget)

from bridge import birlestirici
from bridge.aria2_rpc import Aria2Error, Aria2RPC
from bridge.paths import paket_koku
from ui import autostart, viewmodel

YENILEME_MS = 1000          # polling aralığı
BITEN_KAYIT_SINIRI = 200    # listede + diskte tutulacak en fazla tamamlanan satır
MAKS_BEKLEYEN = 1000        # tellWaiting'de istenecek satır sayısı
HIZ_SECENEKLERI = ["Unlimited", "1 MB/s", "5 MB/s", "10 MB/s", "25 MB/s",
                   "50 MB/s", "Custom…"]
GECMIS_DOSYA = Path(os.environ.get("APPDATA") or Path.home()) \
    / "ai-dl-bridge" / "gecmis.json"

# pastel palet
ZEMIN = "#faf6f0"
KART = "#ffffff"
CIZGI = "#e9e2d6"
METIN = "#57505e"
IKINCI = "#a39dae"

TEM_STILI = f"""
QWidget {{ background: {ZEMIN}; color: {METIN};
    font-family: "Segoe UI"; font-size: 12px; }}
#baslikCubugu {{ background: {KART}; border-bottom: 1px solid {CIZGI}; }}
#pencereBaslik {{ color: {IKINCI}; font-size: 11px; font-weight: bold;
                 padding-left: 12px; letter-spacing: 1px; }}
#aracCubugu {{ background: {KART}; border-bottom: 1px solid {CIZGI}; }}
QToolButton {{ border: 1px solid transparent; border-radius: 8px;
               color: {METIN}; padding: 6px 8px; }}
QToolButton:hover {{ background: #f0e9de; border-color: {CIZGI}; }}
QToolButton::menu-indicator {{ image: none; }}
#kapatDugme:hover {{ background: #f2c9c9; color: #8c3a3a; }}
QListWidget {{ background: {ZEMIN}; border: none; outline: none; }}
QListWidget::item:hover {{ background: #f3ece1; }}
QListWidget::item:selected {{ background: #e7e0f5; }}
#listeKutusu {{ background: {ZEMIN}; border: 1px solid {CIZGI};
               margin: 4px 8px 6px 8px; }}
#kolonCubugu {{ background: {KART}; border-bottom: 1px solid {CIZGI}; }}
QLabel#kolonBaslik, QLabel#kolonAd, QLabel#kolonSag {{
    color: {IKINCI}; font-size: 11px; padding: 4px 8px; }}
QLabel#kolonBaslik:hover, QLabel#kolonAd:hover,
QLabel#kolonSag:hover {{ background: #f0e9de; color: {METIN}; }}
QLabel#kolonBaslik[aktif="true"], QLabel#kolonAd[aktif="true"],
QLabel#kolonSag[aktif="true"] {{ color: #7a6bb5; font-weight: bold; }}
#kolonAd {{ text-align: left; padding-left: 0; }}
#kolonSag {{ text-align: right; padding-right: 0; }}
QProgressBar {{ background: #ede7db; border: none; border-radius: 2px;
               max-height: 4px; min-height: 4px; }}
QProgressBar::chunk {{ border-radius: 2px; }}
QComboBox {{ background: {KART}; border: 1px solid {CIZGI}; border-radius: 6px;
             padding: 4px 8px; min-width: 90px; }}
QComboBox:hover {{ border-color: #b9aed6; }}
QComboBox::drop-down {{ border: none; }}
QMenu {{ background: {KART}; border: 1px solid {CIZGI}; padding: 4px 0; }}
QMenu::item {{ padding: 6px 26px; color: {METIN}; }}
QMenu::item:selected {{ background: #e7e0f5; color: {METIN}; }}
QMenu::item:checked {{ color: #7a6bb5; }}
QMenu::separator {{ height: 1px; background: {CIZGI}; margin: 4px 8px; }}
QToolTip {{ background: {KART}; color: {METIN}; border: 1px solid {CIZGI}; }}
"""


class KolonBaslik(QLabel):
    """Tıklanabilir kolon başlığı — QLabel hizalama (text-align) destekler,
    QToolButton desteklemez."""

    def __init__(self, yazi: str, kolon: str, tikla, parent=None):
        super().__init__(yazi, parent)
        self._kolon = kolon
        self._tikla = tikla
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        self._tikla()
        super().mousePressEvent(event)


def logo_ikonu() -> QIcon:
    """assets/logo.png (şeffaf zemli) varsa onu, yoksa boş ikon döner."""
    yol = paket_koku() / "assets" / "logo.png"
    return QIcon(str(yol)) if yol.exists() else QIcon()


def logo_pixmap(boyut: int) -> QPixmap | None:
    yol = paket_koku() / "assets" / "logo.png"
    if not yol.exists():
        return None
    return QPixmap(str(yol)).scaled(
        boyut, boyut, Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation)


class Pencere(QWidget):
    def __init__(self, rpc: Aria2RPC, sunucu_portu: int,
                 indirme_klasoru: Path | None = None,
                 klasor_secildi=None, parent=None):
        super().__init__(parent)
        self.rpc = rpc
        self.sunucu_portu = sunucu_portu
        if indirme_klasoru:
            self.indirme_klasoru = Path(indirme_klasoru)
        else:
            from bridge.paths import indirme_koku
            self.indirme_klasoru = indirme_koku()
        self.klasor_secildi = klasor_secildi  # run.py'den klasör değişikliği callback'i
        self._secili: dict | None = None      # {gid, durum} seçili satır
        self._yollar: dict[str, str] = {}     # gid -> dosya yolu (klasör açmak için)
        self._onceki_gidler: set[str] = set()
        self._bitenler: dict[str, tuple[float, dict]] = {}  # gid -> (bitiş anı, satır)
        self._hata_sayisi = 0
        self._hata_bildirildi = False
        self._hiz_limit_mb = 0
        self._siralama_kolon = "tarih"   # ad | boyut | tarih
        self._siralama_ters = True       # tarih: yeni önce, boyut: büyük önce
        self._surukleme_konum = None
        self._gid_durum: dict[str, str] = {}  # gid -> durum (yenile'de doluyor)
        self._gecmis_yukle()                  # oturumlar arası tamamlananlar

        self.setWindowTitle("ai-dl-bridge")
        self.setFixedSize(540, 400)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(TEM_STILI)

        self._arayuz_kur()
        self._tepsi_kur()

        self.zamanlayici = QTimer(self)
        self.zamanlayici.timeout.connect(self.yenile)
        self.zamanlayici.start(YENILEME_MS)
        self.yenile()

    # ---------- kurulum ----------

    def _arayuz_kur(self) -> None:
        dis = QVBoxLayout(self)
        dis.setContentsMargins(0, 0, 0, 0)
        dis.setSpacing(0)

        # başlık çubuğu (frameless pencerede sürüklenir)
        ust = QWidget()
        ust.setObjectName("baslikCubugu")
        ust.setFixedHeight(38)
        ust_konum = QHBoxLayout(ust)
        ust_konum.setContentsMargins(0, 0, 0, 0)
        ust_konum.setSpacing(0)
        logo_pm = logo_pixmap(32)
        if logo_pm:
            logo_etiket = QLabel()
            logo_etiket.setPixmap(logo_pm)
            logo_etiket.setStyleSheet("background: transparent; padding-left: 10px;")
            logo_etiket.setToolTip("ai-dl-bridge")
            ust_konum.addWidget(logo_etiket)
        self.baglanti_nokta = QLabel("●")
        self.baglanti_nokta.setStyleSheet("color: #d98c8c; padding-left: 12px;")
        ust_konum.addWidget(self.baglanti_nokta)
        baslik = QLabel("ai-dl-bridge")
        baslik.setObjectName("pencereBaslik")
        ust_konum.addWidget(baslik)
        ust_konum.addStretch(1)
        self.menu_dugme = QToolButton()
        self.menu_dugme.setText("☰")
        self.menu_dugme.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_dugme.setMenu(self._menu_kur())
        ust_konum.addWidget(self.menu_dugme)
        kapat = QToolButton()
        kapat.setObjectName("kapatDugme")
        kapat.setText("✕")
        kapat.setToolTip("Minimize to tray")
        kapat.clicked.connect(self.close)
        ust_konum.addWidget(kapat)
        dis.addWidget(ust)

        # araç çubuğu: Devam / Durdur / Sil / Klasör + hız + sıralama (IDM düzeni)
        arac = QWidget()
        arac.setObjectName("aracCubugu")
        arac.setFixedHeight(64)
        arac_konum = QHBoxLayout(arac)
        arac_konum.setContentsMargins(8, 6, 8, 6)
        arac_konum.setSpacing(4)

        stil = self.style()
        self.devam_dugme = self._arac_dugme(
            arac, stil.standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            "Resume", "Resume the selected download",
            lambda: self._aksiyon_secili("devam"))
        self.durdur_dugme = self._arac_dugme(
            arac, stil.standardIcon(QStyle.StandardPixmap.SP_MediaPause),
            "Pause", "Pause the selected download",
            lambda: self._aksiyon_secili("durdur"))
        self.sil_dugme = self._arac_dugme(
            arac, stil.standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton),
            "Remove", "Cancel the selected download and delete partial files",
            lambda: self._aksiyon_secili("iptal"))
        self.klasor_dugme = self._arac_dugme(
            arac, stil.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
            "Folder", "Open the file's download folder",
            lambda: self._aksiyon_secili("klasor"))
        for d in (self.devam_dugme, self.durdur_dugme, self.sil_dugme,
                  self.klasor_dugme):
            arac_konum.addWidget(d)

        arac_konum.addStretch(1)

        hiz_kutu = QHBoxLayout()
        hiz_kutu.setSpacing(4)
        hiz_etiket = QLabel("Speed:")
        hiz_etiket.setStyleSheet(f"color: {IKINCI}; background: transparent;")
        hiz_kutu.addWidget(hiz_etiket)
        self.hiz_combo = QComboBox()
        self.hiz_combo.addItems(HIZ_SECENEKLERI)
        self.hiz_combo.currentIndexChanged.connect(self._hiz_secildi)
        hiz_kutu.addWidget(self.hiz_combo)
        arac_konum.addLayout(hiz_kutu)
        dis.addWidget(arac)

        # liste kutusu: üstünde tıklanabilir kolon başlıkları (Dosyalar düzeni)
        kutu = QWidget()
        kutu.setObjectName("listeKutusu")
        kutu_lay = QVBoxLayout(kutu)
        kutu_lay.setContentsMargins(0, 0, 0, 0)
        kutu_lay.setSpacing(0)
        kutu_lay.addWidget(self._kolon_cubugu_kur())

        self.liste = QListWidget()
        self.liste.itemSelectionChanged.connect(self._secim_degisti)
        self.liste.itemDoubleClicked.connect(self._cift_tiklandi)
        kutu_lay.addWidget(self.liste, 1)
        dis.addWidget(kutu, 1)

        self.ozet_etiket = QLabel("")
        self.ozet_etiket.setStyleSheet(
            f"color: {IKINCI}; font-size: 11px; padding: 6px 12px;"
            f" border-top: 1px solid {CIZGI};")
        dis.addWidget(self.ozet_etiket)

        # üst bar ve yazıları da sürükleme alanı sayılsın
        for parca in (ust, arac, self.baglanti_nokta, baslik):
            parca.installEventFilter(self)
        self._butonlari_guncelle()

    def _kolon_cubugu_kur(self) -> QWidget:
        """Listenin içindeki kolon başlıkları — tıklayınca sıralar."""
        cubuk = QWidget()
        cubuk.setObjectName("kolonCubugu")
        cubuk.setFixedHeight(28)
        lay = QHBoxLayout(cubuk)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(4)

        def baslik(yazi: str, kolon: str, esnek: bool = False,
                   genislik: int | None = None, nesne_ad: str = "") -> QLabel:
            d = KolonBaslik(yazi, kolon,
                            lambda: self._kolona_gore_sirala(kolon))
            d.setObjectName(nesne_ad or "kolonBaslik")
            if genislik:
                d.setFixedWidth(genislik)
            d.setToolTip(f"Sort by {yazi} (click again to reverse)")
            if esnek:
                d.setAlignment(Qt.AlignmentFlag.AlignLeft
                               | Qt.AlignmentFlag.AlignVCenter)
                lay.addWidget(d, 1)
            else:
                d.setAlignment(Qt.AlignmentFlag.AlignRight
                               | Qt.AlignmentFlag.AlignVCenter)
                lay.addWidget(d)
            return d

        self.kolon_ad = baslik("Name", "ad", esnek=True, nesne_ad="kolonAd")
        self.kolon_boyut = baslik("Size", "boyut", genislik=90, nesne_ad="kolonSag")
        self.kolon_tarih = baslik("Date", "tarih", genislik=110, nesne_ad="kolonSag")
        self._kolonlari_guncelle()
        return cubuk

    def _kolona_gore_sirala(self, kolon: str) -> None:
        """Aynı kolona tekrar basınca yön değişir; yeni kolon öntanımlı yönle açılır."""
        if self._siralama_kolon == kolon:
            self._siralama_ters = not self._siralama_ters
        else:
            self._siralama_kolon = kolon
            self._siralama_ters = kolon != "ad"  # ad: A→Z, diğerleri: büyük/yeni önce
        self._kolonlari_guncelle()
        self.yenile()

    def _kolonlari_guncelle(self) -> None:
        ok = {"ad": self.kolon_ad, "boyut": self.kolon_boyut,
              "tarih": self.kolon_tarih}
        temel = {"ad": "Name", "boyut": "Size", "tarih": "Date"}
        for kolon, d in ok.items():
            aktif = kolon == self._siralama_kolon
            d.setProperty("aktif", "true" if aktif else "false")
            d.setText(temel[kolon] + ((" ▾" if self._siralama_ters else " ▴")
                                      if aktif else ""))
            d.style().unpolish(d)
            d.style().polish(d)

    def _siralama_anahtar(self, s: dict):
        if self._siralama_kolon == "ad":
            return s.get("baslik", "").lower()
        if self._siralama_kolon == "boyut":
            return s.get("boyut", 0)
        return s.get("zaman", 0)

    def _arac_dugme(self, parent, ikon, yazi, ipucu, baglan) -> QToolButton:
        d = QToolButton(parent)
        d.setIcon(ikon)
        d.setText(yazi)
        d.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        d.setToolTip(ipucu)
        d.setIconSize(QSize(18, 18))
        d.setFixedSize(58, 50)
        d.setStyleSheet("QToolButton { font-size: 11px; }")
        d.clicked.connect(baglan)
        d.setEnabled(False)
        return d

    def _menu_kur(self) -> QMenu:
        menu = QMenu(self)
        self.ustte_action = menu.addAction("Always on top")
        self.ustte_action.setCheckable(True)
        self.ustte_action.toggled.connect(self._ustte_toggled)

        self.otostart_action = menu.addAction("Start with Windows")
        self.otostart_action.setCheckable(True)
        self.otostart_action.setChecked(autostart.aktif_mi())
        self.otostart_action.toggled.connect(self._otostart_toggled)

        menu.addAction("Download folder…", self._klasor_sec)
        menu.addAction("Connection info for AIs…", self._baglanti_bilgisi)
        menu.addSeparator()
        menu.addAction("Quit", QApplication.quit)
        return menu

    def _tepsi_kur(self) -> None:
        ikon = logo_ikonu()
        if ikon.isNull():
            ikon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        self.setWindowIcon(ikon)
        self.tepsi = QSystemTrayIcon(ikon, self)
        tepsi_menu = QMenu()
        tepsi_menu.addAction("Show", self._goster)
        tepsi_menu.addAction("Quit", QApplication.quit)
        self.tepsi.setContextMenu(tepsi_menu)
        self.tepsi.activated.connect(
            lambda n: self._goster() if n == QSystemTrayIcon.ActivationReason.Trigger
            else None)
        self.tepsi.show()

    # ---------- araç çubuğu mantığı ----------

    def _butonlari_guncelle(self) -> None:
        """Seçili satırın durumuna göre butonları aç/kapat."""
        sec = self._secili
        if not sec:
            self.devam_dugme.setEnabled(False)
            self.durdur_dugme.setEnabled(False)
            self.sil_dugme.setEnabled(False)
            self.klasor_dugme.setEnabled(False)
            return
        gid = sec["gid"]
        durum = sec.get("durum", "")
        self.devam_dugme.setEnabled(durum == "paused")
        self.durdur_dugme.setEnabled(durum == "active")
        self.klasor_dugme.setEnabled(bool(self._yollar.get(gid)))
        if gid in self._bitenler:
            # tamamlanan satır: dosyaya dokunmadan listeden kaldır
            self.sil_dugme.setToolTip("Remove from list (file is kept)")
        else:
            self.sil_dugme.setToolTip("Cancel download and delete partial files")
        self.sil_dugme.setEnabled(True)

    def _secim_degisti(self) -> None:
        item = self.liste.currentItem()
        gid = item.data(Qt.ItemDataRole.UserRole) if item else None
        if gid:
            self._secili = {"gid": gid, "durum": self._gid_durum.get(gid, "")}
        else:
            self._secili = None
        self._butonlari_guncelle()

    def _aksiyon_secili(self, aksiyon: str) -> None:
        if not self._secili:
            return
        gid = self._secili["gid"]
        try:
            if aksiyon == "durdur":
                self.rpc.pause(gid)
            elif aksiyon == "devam":
                self.rpc.unpause(gid)
            elif aksiyon == "iptal":
                self._iptal(gid)
                self._secili = None
            elif aksiyon == "klasor":
                self._klasor_ac(gid)
        except Aria2Error as e:
            self.tepsi.showMessage("ai-dl-bridge", f"Operation failed: {e}",
                                   QSystemTrayIcon.MessageIcon.Warning, 3000)
        self.yenile()

    def _hiz_secildi(self, indeks: int) -> None:
        secim = HIZ_SECENEKLERI[indeks]
        if secim == "Custom…":
            deger, ok = QInputDialog.getDouble(
                self, "Speed limit", "MB/s (0 = unlimited):",
                float(self._hiz_limit_mb), 0, 1024, 0)
            if ok:
                self._hiz_limit_mb = int(deger)
                self._hiz_uygula()
                ozel_ind = self.hiz_combo.count() - 1
                self.hiz_combo.blockSignals(True)
                self.hiz_combo.setItemText(ozel_ind, f"{self._hiz_limit_mb} MB/s (custom)")
                self.hiz_combo.setCurrentIndex(ozel_ind)
                self.hiz_combo.blockSignals(False)
            return
        self._hiz_limit_mb = 0 if indeks == 0 else int(secim.split()[0])
        self._hiz_uygula()

    def _hiz_uygula(self) -> None:
        try:
            self.rpc.set_speed_limit(self._hiz_limit_mb * 1024 * 1024)
        except Aria2Error as e:
            QMessageBox.warning(self, "Hız limiti", str(e))

    # ---------- başlık çubuğu sürükleme ----------

    def eventFilter(self, obj, event):
        """Üst barın (ve üzerindeki yazıların) sürüklenmesi."""
        if event.type() == QEvent.Type.MouseButtonPress and \
                event.button() == Qt.MouseButton.LeftButton:
            self._surukleme_konum = event.globalPosition().toPoint() - self.pos()
        elif event.type() == QEvent.Type.MouseMove and \
                self._surukleme_konum is not None and \
                event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._surukleme_konum)
        elif event.type() == QEvent.Type.MouseButtonRelease:
            self._surukleme_konum = None
        return False  # olayı asıl hedefe de ilet

    # ---------- yenileme ----------

    def yenile(self) -> None:
        try:
            aktif = self.rpc.tell_active()
            bekleyen = self.rpc.tell_waiting(0, MAKS_BEKLEYEN)
        except Aria2Error:
            self._hata_sayisi += 1
            self.baglanti_nokta.setStyleSheet("color: #d98c8c; padding-left: 12px;")
            if self._hata_sayisi >= 3 and not self._hata_bildirildi:
                self._hata_bildirildi = True
                self.tepsi.showMessage(
                    "ai-dl-bridge", "aria2 connection lost.",
                    QSystemTrayIcon.MessageIcon.Warning, 3000)
            return

        self._hata_sayisi = 0
        self._hata_bildirildi = False
        self.baglanti_nokta.setStyleSheet("color: #6fbf9e; padding-left: 12px;")

        durumlar = aktif + bekleyen
        simdiki_gidler = {d.get("gid") for d in durumlar}
        self._bitenleri_yakala(simdiki_gidler, durumlar)
        self._durdurulmuslari_isle()
        birlestirici.bekleyenleri_isle(self.rpc, self._birlesme_biti)
        self._onceki_gidler = simdiki_gidler

        satirlar = [viewmodel.satir_yap(d) for d in durumlar]
        self._gid_durum = {s["gid"]: s["durum"] for s in satirlar}
        for s, d in zip(satirlar, durumlar):
            dosya = (d.get("files") or [{}])[0]
            if dosya.get("path"):
                self._yollar[s["gid"]] = dosya["path"]

        for gid, (an, satir) in self._bitenler.items():
            if gid not in simdiki_gidler:
                satirlar.append(satir)

        # sıralama: inen işler doğal sıradan üstte, tamamlananlar kolon başlığına göre
        tamamlananlar = [s for s in satirlar if s.get("bitti")]
        digerleri = [s for s in satirlar if not s.get("bitti")]
        tamamlananlar.sort(key=self._siralama_anahtar,
                           reverse=self._siralama_ters)
        self._listeyi_doldur(digerleri + tamamlananlar)

        o = viewmodel.ozet(satirlar)
        kalan = viewmodel.boyut_format(o["kalan_bayt"]) if o["kalan_bayt"] else "0"
        bek = f" · {o['bekleyen']} queued" if o["bekleyen"] else ""
        self.ozet_etiket.setText(
            f"{o['aktif']} downloading{bek} · {viewmodel.hiz_format(o['toplam_hiz_bayt'])}"
            f" · {kalan} left")

    def _bitenleri_yakala(self, simdiki: set, durumlar: list) -> None:
        """Önceki turda olup şimdi kuyrukta görünmeyen gid'leri sor."""
        parcalar = birlestirici.parca_gidleri()
        for gid in self._onceki_gidler - simdiki:
            if gid in parcalar:
                continue  # video birleştirme parçası — ayrıca takip ediliyor
            try:
                durum = self.rpc.tell_status(gid)
            except Aria2Error:
                continue  # kuyruktan düştüyse sonuç da silinmiştir
            if durum.get("status") == "complete":
                self._biten_ekle(gid, durum)

    def _durdurulmuslari_isle(self) -> None:
        """Iki poll arasinda biten kucuk dosyalari yakala (race kapatma).

        Saniyeden hizli inen dosyalar aktif listesinde hic gorunmez; aria2'nin
        'stopped' sonuc listesinden tamamlananlari toplar.
        """
        try:
            durdurulanlar = self.rpc.tell_stopped(0, MAKS_BEKLEYEN)
        except Aria2Error:
            return
        parcalar = birlestirici.parca_gidleri()
        for durum in durdurulanlar:
            gid = durum.get("gid")
            if not gid or gid in self._bitenler or gid in parcalar:
                continue
            if durum.get("status") == "complete":
                self._biten_ekle(gid, durum)
            else:
                # hata/iptal sonuclarini kuyruktan temizle (biz silmediysek)
                try:
                    self.rpc.remove_download_result(gid)
                except Aria2Error:
                    pass

    def _birlesme_biti(self, job: dict) -> None:
        """ffmpeg birleşmesi bitince tek satır olarak geçmişe işle."""
        gid = job.get("video_gid") or job.get("anahtar")
        try:
            boyut = Path(job["hedef"]).stat().st_size
        except OSError:
            boyut = job.get("boyut") or 0
        simdi = time.time()
        self._yollar[gid] = job["hedef"]
        satir = {"gid": gid, "baslik": job.get("baslik", "?"), "yuzde": 100,
                 "hiz": "done", "durum": "complete",
                 "renk": viewmodel.RENKLER["complete"], "bitti": True, "kalan": 0,
                 "zaman": simdi, "boyut": boyut, "aksiyonlar": [], "_hiz_bayt": 0}
        self._bitenler[gid] = (simdi, satir)
        self._gecmis_kaydet(gid, satir, job["hedef"])

    def _biten_ekle(self, gid: str, durum: dict) -> None:
        """Tamamlanan sonucu listeye + kalici gecmise isler, kuyruktan temizler."""
        satir = viewmodel.satir_yap(durum)
        satir["bitti"] = True
        satir["aksiyonlar"] = []
        satir["renk"] = viewmodel.RENKLER["complete"]
        satir["hiz"] = "done"
        satir["zaman"] = time.time()
        satir["boyut"] = int(durum.get("totalLength", 0))
        yol = (durum.get("files") or [{}])[0].get("path")
        if yol:
            self._yollar[gid] = yol
        self._bitenler[gid] = (time.time(), satir)
        while len(self._bitenler) > BITEN_KAYIT_SINIRI:
            self._bitenler.pop(next(iter(self._bitenler)))
        self._gecmis_kaydet(gid, satir, yol)
        try:
            self.rpc.remove_download_result(gid)
        except Aria2Error:
            pass

    # ---------- kalıcı geçmiş ----------

    def _gecmis_oku(self) -> list:
        try:
            kayitlar = json.loads(GECMIS_DOSYA.read_text(encoding="utf-8"))
            return kayitlar if isinstance(kayitlar, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _gecmis_yukle(self) -> None:
        """Diskteki tamamlananları listeye geri koy (oturumlar arası kalıcılık)."""
        for k in self._gecmis_oku():
            gid = k.get("gid")
            if not gid or gid in self._bitenler:
                continue
            self._yollar[gid] = k.get("yol") or ""
            self._bitenler[gid] = (0.0, {
                "gid": gid, "baslik": k.get("baslik", "?"), "yuzde": 100,
                "hiz": "done", "durum": "complete",
                "renk": viewmodel.RENKLER["complete"], "bitti": True, "kalan": 0,
                "zaman": k.get("zaman", 0), "boyut": k.get("boyut", 0),
                "aksiyonlar": [], "_hiz_bayt": 0})

    def _gecmis_kaydet(self, gid: str, satir: dict, yol: str | None) -> None:
        try:
            kayitlar = [k for k in self._gecmis_oku() if k.get("gid") != gid]
            kayitlar.append({"gid": gid, "baslik": satir.get("baslik", "?"),
                             "yol": yol or "", "zaman": satir.get("zaman", time.time()),
                             "boyut": satir.get("boyut", 0)})
            GECMIS_DOSYA.parent.mkdir(parents=True, exist_ok=True)
            GECMIS_DOSYA.write_text(
                json.dumps(kayitlar[-BITEN_KAYIT_SINIRI:],
                           ensure_ascii=False, indent=1),
                encoding="utf-8")
        except OSError:
            pass  # geçmiş yazılamazsa indirme yine de başarılı sayılır

    def _gecmis_sil(self, gid: str) -> None:
        try:
            kayitlar = [k for k in self._gecmis_oku() if k.get("gid") != gid]
            GECMIS_DOSYA.write_text(
                json.dumps(kayitlar, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except OSError:
            pass

    # ---------- liste ----------

    def _listeyi_doldur(self, satirlar: list) -> None:
        secili_gid = self._secili["gid"] if self._secili else None
        self.liste.blockSignals(True)
        self.liste.clear()
        for s in satirlar:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, s["gid"])
            widget = self._satir_widget(s)
            item.setSizeHint(widget.sizeHint())
            self.liste.addItem(item)
            self.liste.setItemWidget(item, widget)
            if s["gid"] == secili_gid:
                self.liste.setCurrentItem(item)
        if not satirlar:
            bos = QListWidgetItem()
            bos.setFlags(Qt.ItemFlag.NoItemFlags)
            yazi = QLabel("No downloads\n\n"
                          f"AI agents POST to 127.0.0.1:{self.sunucu_portu}/indir"
                          "\nand their downloads appear here")
            yazi.setAlignment(Qt.AlignmentFlag.AlignCenter)
            yazi.setStyleSheet(f"color: {IKINCI}; font-size: 12px; background: transparent;")
            yazi.setFixedHeight(300)
            self.liste.addItem(bos)
            self.liste.setItemWidget(bos, yazi)
        self.liste.blockSignals(False)
        self._secim_degisti()

    def _satir_widget(self, s: dict) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")  # seçili satır rengi görünsün
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)

        ust = QHBoxLayout()
        ust.setSpacing(4)
        isaret = "✔ " if s.get("bitti") else ""
        sol = QLabel(f"{isaret}{s['baslik']}")
        sol.setStyleSheet(f"color: {s['renk']}; font-weight: bold; background: transparent;")
        sol.setToolTip(self._yollar.get(s["gid"], s["baslik"]))
        ust.addWidget(sol, 4)  # isim ~%80

        detay_stil = (f"color: {IKINCI}; font-size: 10px; background: transparent;")
        if s.get("bitti"):
            boyut = viewmodel.boyut_format(s["boyut"]) if s.get("boyut") else "—"
            damga = time.strftime("%d.%m %H:%M",
                                  time.localtime(s.get("zaman") or time.time()))
            sag_boyut = QLabel(boyut)
            sag_tarih = QLabel(damga)
        else:
            sag_boyut = QLabel(f"%{s['yuzde']}")
            sag_tarih = QLabel(s["hiz"])
        for etiket, genislik in ((sag_boyut, 90), (sag_tarih, 110)):
            etiket.setStyleSheet(detay_stil)
            etiket.setFixedWidth(genislik)
            etiket.setAlignment(Qt.AlignmentFlag.AlignRight
                                | Qt.AlignmentFlag.AlignVCenter)
            ust.addWidget(etiket)
        lay.addLayout(ust)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(100 if s.get("bitti") else s["yuzde"])
        bar.setTextVisible(False)
        bar.setStyleSheet(f"QProgressBar::chunk {{ background: {s['renk']}; }}")
        lay.addWidget(bar)
        return w

    # ---------- etkileşim ----------

    def _klasor_ac(self, gid: str) -> None:
        yol = self._yollar.get(gid)
        if yol:
            # dosya silinmişse de sessizce tolere eder
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(yol).parent)))

    def _cift_tiklandi(self, item: QListWidgetItem) -> None:
        self._klasor_ac(item.data(Qt.ItemDataRole.UserRole))

    def _iptal(self, gid: str) -> None:
        """Tamamlanan satırı yalnız listeden kaldırır; inen işi iptal edip
        yarım dosyayı temizler."""
        if gid in self._bitenler:
            self._bitenler.pop(gid, None)
            self._yollar.pop(gid, None)
            self._gecmis_sil(gid)
            return
        yol = self._yollar.get(gid)
        try:
            self.rpc.remove(gid)
        except Aria2Error:
            pass  # listedeki durumuna göre zaten kalkmış olabilir
        try:
            self.rpc.remove_download_result(gid)
        except Aria2Error:
            pass
        if yol:
            for artik in (Path(yol), Path(str(yol) + ".aria2")):
                try:
                    artik.unlink(missing_ok=True)
                except OSError:
                    pass

    # ---------- menü ----------

    def _ustte_toggled(self, acik: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, acik)
        self.show()

    def _otostart_toggled(self, acik: bool) -> None:
        if acik:
            autostart.etkinlestir()
        else:
            autostart.devre_disi_birak()

    def _klasor_sec(self) -> None:
        yeni = QFileDialog.getExistingDirectory(
            self, "Download folder", str(self.indirme_klasoru))
        if yeni:
            self.indirme_klasoru = Path(yeni)
            if self.klasor_secildi:
                self.klasor_secildi(yeni)

    def _baglanti_bilgisi(self) -> None:
        adres = f"http://127.0.0.1:{self.sunucu_portu}/indir"
        ornek = json.dumps({"link": "https://example.com/file.zip",
                            "kimlik": "my-ai"}, indent=2)
        metin = (f"AI agents POST to this address:\n\n  {adres}\n\n"
                 f"Body (JSON):\n{ornek}\n\n"
                 f"curl example:\n"
                 f'  curl -X POST {adres} -H "Content-Type: application/json"'
                 f' -d "{ornek.replace(chr(10), " ")}"')
        QMessageBox.information(self, "Connection info for AIs", metin)

    # ---------- pencere/tepsi davranışı ----------

    def _goster(self) -> None:
        self.show()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()
        if self.tepsi.isVisible():
            self.tepsi.showMessage(
                "ai-dl-bridge", "Still running in the background.",
                QSystemTrayIcon.MessageIcon.Information, 2500)


def main() -> int:
    """Bağımsız deneme: aria2 zaten çalışıyorsa sadece pencereyi açar."""
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("ai-dl-bridge")
    app.setQuitOnLastWindowClosed(False)
    pencere = Pencere(rpc=Aria2RPC(), sunucu_portu=8765)
    pencere.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
