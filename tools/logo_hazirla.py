"""ADLB logosu: siyah+beyaz sil, kırmızıyı şeffaf zemli PNG/ICO yap.

Kullanıcının çizimi: kırmızı ana hatlar (logo), siyah taslak çizgileri
(silinecek), beyaz zemin (şeffaf olacak).
"""
from pathlib import Path

from PIL import Image, ImageFilter

KAYNAK = Path.home() / "Desktop" / "ADLB.png"
PROJE = Path(__file__).resolve().parent.parent
CIKTI = PROJE / "assets"
CIKTI.mkdir(exist_ok=True)


def kirmizi_maske(piksel):
    r, g, b = piksel[0], piksel[1], piksel[2]
    return r > 110 and r - max(g, b) > 55   # doygun kırmızı şartı


def main():
    im = Image.open(KAYNAK).convert("RGBA")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, _ = px[x, y]
            if kirmizi_maske((r, g, b)):
                px[x, y] = (r, g, b, 255)     # kırmızı: koru
            else:
                px[x, y] = (0, 0, 0, 0)       # siyah/beyaz/gri: şeffaf

    # kırmızı içeriğin sınır kutusuna kırp + ince çizgileri kalınlaştır
    # (küçük ikon boyutlarında okunaklılık için) + kare tuval ortala
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    r, g, b, a = im.split()
    a = a.filter(ImageFilter.MaxFilter(9))   # stroke'u ~4px şişirir
    im = Image.merge("RGBA", (r, g, b, a))
    kenar = max(im.size) + 8
    tuval = Image.new("RGBA", (kenar, kenar), (0, 0, 0, 0))
    tuval.paste(im, ((kenar - im.width) // 2, (kenar - im.height) // 2), im)

    png_yol = CIKTI / "logo.png"
    tuval.save(png_yol)
    ico_yol = CIKTI / "logo.ico"
    tuval.save(ico_yol, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                               (128, 128), (256, 256)])
    print("PNG:", png_yol, tuval.size)
    print("ICO:", ico_yol)


if __name__ == "__main__":
    main()
