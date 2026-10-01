---
name: ai-indirme-koprusu
description: Web'den dosya, video, veri seti veya arşiv indirirken AI İndirme Köprüsü (ai-dl-bridge) üzerinden indirmek. Kullanıcının kendi bilgisayarında çalışan, tüm AI indirmelerini tek pencerede gösteren localhost indirme yöneticisi (aria2 + yt-dlp). Bir şey indirmek gerektiğinde (veri seti, PDF, zip, YouTube videosu, müzik, büyük dosya) bu skill kullanılır; doğrudan curl/wget/urllib ile kullanıcı adına dosya indirilmez.
---

# AI İndirme Köprüsü ile İndirme

Kullanıcının kuralı: **AI'ın indireceği her şey bu uygulama üzerinden iner.** Amaç, tüm
AI indirmelerinin kullanıcının tek penceresinde (IDM tarzı arayüz) görünmesi ve
durdurulabilmesi.

## Zorunlu akış

1. `scripts/kopru_indir.py` betiğini çalıştır:

   ```bash
   python <skill-koku>/scripts/kopru_indir.py "<URL>" --bekle
   ```

2. `--bekle` sonucu `TAMAM: <yol> (<boyut>)` verene dek bekle; dosya yolunu kullanıcıya bildir.
3. Sunucu kapalıysa betik exe'yi `--gizli` kipte kendi başlatır; hiçbir şey yapmana gerek yok.

## Parametreler

- `--kalite video` (varsayılan): gerçek video. En iyi görüntü + en iyi ses akışı
  ayrı ayrı iner, uygulama ffmpeg ile tek mp4'ta birleştirir (DASH çağında tek
  akışta sesli yüksek kalite yoktur).
- `--kalite ses`: en iyi ses akışı (m4a) — şarkılar için.
- `--kalite eniyi`: en iyi TEK dosya akışı (birleşik akış varsa; yoksa sessiz görüntü).
- `--kalite endusuk`: hızlı testlerde en küçük direkt indirilebilir dosya.
- `--kimlik`: listede görünecek AI adı (ör. `kimi`).

## Çıktı yeri

`downloads/` (uygulamanın kendi içindeki klasör — exe yanı / proje kökü) — indirme büyükse sunucu kuyruğa alabilir;
betik bir kez otomatik devam ettirir.

## Ne zaman bu skill kullanılmaz

- `pip install`, `npm install`, `git clone` gibi paket yöneticisi işlemleri (sistem
  seviyesinde, köprü kapsamı dışı).
- API'den dönen küçük JSON/yanıt okumaları (dosya indirme değil).
- Test ortamında mock'lanan indirmeler.

Bunların dışında kullanıcı adına bir dosya inecekse HER ZAMAN bu köprüden indir.
