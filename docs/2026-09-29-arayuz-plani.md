# PyQt6 Arayüz Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ai-dl-bridge mini penceresi — AI'ların indirmelerini listeleme, tıkla-durdur/devam/iptal, hız limiti, tepsi ikonu.

**Architecture:** aria2c daemon + FastAPI sunucusu arka planda; PyQt6 pencere yalnızca aria2 RPC'den okur ve kullanıcı aksiyonunu RPC'ye yazar. Tüm saf mantık viewmodel katmanında (test edilebilir, GUI'siz).

**Tech Stack:** Python 3.12, PyQt6, FastAPI+uvicorn (thread), aria2 RPC (bridge/aria2_rpc.py — mevcut)

**Spec:** `docs/2026-09-28-tasarim.md` §1, §3, §6

> **Durum (2026-09-29):** Tüm task'lar tamam. 28/28 test yeşil; gerçek aria2c 1.37.0 `tools/` altında. Uçtan uca doğrulama: `python run.py` → daemon + sunucu (8765) + pencere; `POST /indir` canlı yanıt verdi; arayüz görseli `docs/ekran-arayuz.png`. Review Focus maddelerinin tamamı kodda + testte karşılıklı.

## Global Constraints
- Pencere ~420×360 piksel; mini, IDM hissi (spec §3)
- Sunucu yalnız 127.0.0.1 (spec §1); port 8765+, doluysa sıradaki boş (spec §6)
- Satır: sol link (orta kesik), sağ `%47 + 2.1 MB/s` (spec §3)
- Renkler: yeşil=indiyor, sarı=duraklatıldı, kırmızı=hata, gri ✔=bitti
- Tek tık → aksiyon şeridi (▶ Devam / ⏸ Durdur / ✖ İptal); çift tık → klasörde göster
- Polling 1 sn; alt şerit: aktif sayı + toplam hız + kalan boyut
- yt-dlp INDIRMEZ (spec §2 kritik ilke) — arayüz işi değil, zaten resolver'da

## Review Focus
1. aria2 kapalıyken pencere açılırsa: hata düşer, kullanıcıya anlaşılır mesaj — test: daemon bulunamadı yolu
2. % hesabı: totalLength=0 (henüz bilinmiyor) bölme hatası yapmamalı
3. Hız formatı: 0 bayt/sn gösterimi "0 B/s", 1536 → "1.5 KB/s"
4. Satır tıklaması aynı satırda tekrarlanınca şerit kapanmalı (toggle)
5. İptal edilen indirme listeden düşmeli, klasörü açılan dosya silinmişse sessizce tolere

---

### Task 1: Daemon yöneticisi (`ui/daemon.py`)

**Files:**
- Create: `ui/daemon.py`
- Test: `tests/test_daemon.py`

**Interfaces:**
- Produces: `class Aria2Daemon: start() -> None; stop() -> None; port: int; healthy() -> bool`
- Consumes: aria2c binary yolu (`tools/aria2c.exe` → PATH fallback)

- [x] **Step 1: Failing test — binary bulunamayınca AçıklamalıHata**
- [x] **Step 2: Test fail doğrula**
- [x] **Step 3: Implement binary bulma + spawn + sağlık kontrolü**
- [x] **Step 4: Test pass doğrula**

### Task 2: ViewModel (`ui/viewmodel.py`) — saf mantık

**Files:**
- Create: `ui/viewmodel.py`
- Test: `tests/test_viewmodel.py`

**Interfaces:**
- Produces:
  - `def kisalt(link: str, uzunluk: int = 32) -> str` — `youtube.com/…xyz123`
  - `def hiz_format(bayt_sn: int) -> str` — `2.1 MB/s`
  - `def yuzde(tamamlanan: int, toplam: int) -> int` — 0 bölme güvenli
  - `def satir_yap(durum: dict) -> dict` — {baslik, yuzde, hiz, renk, aksiyonlar}
  - `def ozet(satirlar: list[dict]) -> dict` — {aktif, toplam_hiz, kalan}

- [x] **Step 1-5: TDD ile implement** (testler aşağıda, hepsi yeşil)

### Task 3: Pencere iskeleti (`ui/app.py`)

**Files:**
- Create: `ui/app.py`, `ui/__init__.py`
- Modify: `run.py`

**Interfaces:**
- Consumes: viewmodel fonksiyonları, Aria2RPC (bridge), Aria2Daemon
- Produces: `def main() -> int`

- [x] **Step 1:** Liste (QListWidget) + alt şerit (QLabel) + 1 sn QTimer polling
- [x] **Step 2:** Tek tık → aksiyon şeridi (inline butonlar), çift tık → klasörde göster
- [x] **Step 3:** Menü ☰: hız limiti (sınırsız/1/5/10/25/50/özel), her zaman üstte, bağlantı bilgisi, indirilenler klasörü
- [x] **Step 4:** Sistem tepsisi ikonu (kapatınca tepsiye çekil)
- [x] **Step 5:** run.py: daemon + uvicorn (thread) + pencere sıralı başlat

### Task 4: Bütünleşik test (gerçek aria2 + yerel dosya sunucusu)

**Files:**
- Create: `tests/test_integration.py`

- [x] **Step 1:** Yerel HTTP sunucusundan dosya indirt, listede % ve hız gör
- [x] **Step 2:** Durdur → devam → iptal akışını RPC üzerinden doğrula
