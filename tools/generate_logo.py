"""Generate logo PNG and ICO assets with transparent background."""
from pathlib import Path

from PIL import Image, ImageFilter

SOURCE = Path.home() / "Desktop" / "ADLB.png"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "assets"
OUTPUT_DIR.mkdir(exist_ok=True)


def red_mask(pixel):
    r, g, b = pixel[0], pixel[1], pixel[2]
    return r > 110 and r - max(g, b) > 55   # saturated red condition


def main():
    if not SOURCE.exists():
        print(f"Source file not found at {SOURCE}")
        return

    im = Image.open(SOURCE).convert("RGBA")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, _ = px[x, y]
            if red_mask((r, g, b)):
                px[x, y] = (r, g, b, 255)
            else:
                px[x, y] = (0, 0, 0, 0)

    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    r, g, b, a = im.split()
    a = a.filter(ImageFilter.MaxFilter(9))
    im = Image.merge("RGBA", (r, g, b, a))
    size = max(im.size) + 8
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)

    png_path = OUTPUT_DIR / "logo.png"
    canvas.save(png_path)
    ico_path = OUTPUT_DIR / "logo.ico"
    canvas.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                (128, 128), (256, 256)])
    print("PNG:", png_path, canvas.size)
    print("ICO:", ico_path)


if __name__ == "__main__":
    main()
