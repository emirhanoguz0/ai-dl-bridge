# Binary'ler (tools/)

Bu klasördeki üç binary GitHub'a yüklenmez (`.gitignore`). Yeni bir kopya
kurarken aynı dosya adlarıyla buraya koyun:

| Dosya | İndirme kaynağı |
|---|---|
| `aria2c.exe` | https://github.com/aria2/aria2/releases (win-64bit) |
| `yt-dlp.exe` | https://github.com/yt-dlp/yt-dlp/releases (yt-dlp.exe) |
| `ffmpeg.exe` | https://github.com/BtbN/FFmpeg-Builds/releases (`...-win64-gpl.zip` içinden `bin/ffmpeg.exe`) |

Üçü de taşınabilir (kurulum gerektirmez). `aria2c` ve `ffmpeg` isteğe bağlı
olarak PATH'te de olabilir; yoksa gömülü olanlar kullanılır — ama video
birleştirme için `ffmpeg.exe` bu klasörde bulunmalıdır.

Logo yeniden üretmek isterseniz: `python tools/logo_hazirla.py`
(kaynak çizim masaüstündeki `ADLB.png`yi okur).
