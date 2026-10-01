# AI-DL-Bridge — Uygulama Planı

Spec: `docs/2026-09-28-tasarim.md` (onaylı 2026-09-28)

## Aşamalar
1. **İskelet + plan** — klasör yapısı, requirements, PLAN.md ✅ bu dosya
2. **Çekirdek (test edilebilir, GUI'siz):**
   - `bridge/aria2_rpc.py` — aria2 JSON-RPC istemcisi (addUri, tellStatus,
     pause/unpause/remove, globalSpeedLimit) — saf Python, requests/urllib
   - `bridge/resolver.py` — link sınıflandırma (video sitesi listesi) + yt-dlp
     çağrısı (`yt-dlp --get-url --get-title --no-playlist -J`) — arayüz: çözülen
     link + başlık + tahmini boyut; yt-dlp yoksa/bozuksa AçıklamalıHata
   - `bridge/policy.py` — tek kural: boyut > 2GB → "onay bekliyor"; kural
     altyapısı genişletilebilir liste
   - `bridge/server.py` — FastAPI: `POST /indir` (port seçimi: 8765+, localhost-only)
3. **Birim testleri (internetsiz):** sahte aria2 yanıtlarıyla rpc istemcisi; policy
   sınırları; resolver'ın sahte yt-dlp çıktısıyla davranışı
4. **Pencere (PyQt6):** sistem tepsisi ikonu, liste satırları (link/%/hız/renk),
   tıkla-aksiyon şeridi, menü (hız limiti, başlangıçta çalıştır, bağlantı bilgisi,
   klasör seçimi), alt durum şeridi, 1 sn polling
5. **Bütünleşik test:** gerçek aria2 + yerel dosya sunucusu (localhost→localhost)
6. **Paketleme:** PyInstaller spec (tek exe, tools/ gömülü) — son aşama

## Dosya Yapısı
```
ai-dl-bridge/
├── docs/2026-09-28-tasarim.md
├── PLAN.md
├── requirements.txt
├── run.py
├── bridge/{__init__,aria2_rpc,resolver,policy,server}.py
├── ui/{__init__,app,widgets}.py
├── tools/            (aria2c.exe, yt-dlp.exe — gitignore)
└── tests/{test_policy,test_rpc,test_resolver}.py
```

## Notlar
- yt-dlp INDIRMEZ, sadece `--get-url` ile düz link üretir (spec §2 kritik ilke)
- Tüm hatalar AI'a açıklamalı döner (spec §6)
- Repo adı: `ai-dl-bridge` (GitHub, uluslararası)
