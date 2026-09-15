from pathlib import Path
import sys
import json

import pypdfium2 as pdfium
from PIL import Image, ImageChops, ImageDraw
from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8")
folder = Path(__file__).resolve().parents[1] / "论文初稿/排版检查"
new = pdfium.PdfDocument(folder / "正式版_排版检查.pdf")
old = pdfium.PdfDocument(folder / "排版前_对照.pdf")
cover_new = new[0].render(scale=1.5).to_pil().convert("RGB")
cover_old = old[0].render(scale=1.5).to_pil().convert("RGB")
same_cover = cover_old.size == cover_new.size and ImageChops.difference(cover_new, cover_old).getbbox() is None
print("封面逐像素一致:", same_cover)
assert same_cover, "Cover rendering changed"
montage = Image.new("RGB", (3 * 330, 3 * 485), "#ddd")
draw = ImageDraw.Draw(montage)
reader = PdfReader(folder / "正式版_排版检查.pdf")
for i in range(len(new)):
    im = new[i].render(scale=1.4).to_pil().convert("RGB")
    if i in (1, 2, 3, 4, 7, 8):
        im.save(folder / f"page_{i+1}.png")
    im.thumbnail((310, 448))
    x, y = (i % 3) * 330 + 10, (i // 3) * 485 + 25
    montage.paste(im, (x, y))
    draw.text((x, y - 18), f"Page {i+1}", fill="black")
    t = reader.pages[i].extract_text() or ""
    print(json.dumps({"page": i+1, "first": t[:125], "last": t[-125:]}, ensure_ascii=False))
montage.save(folder / "全部页面检查.png")
