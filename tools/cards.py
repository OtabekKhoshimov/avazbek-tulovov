"""Har bir maqola uchun brendli 1200×1200 rasm-kartochka yasaydi (Pillow).
from __future__ import annotations

    python3 tools/cards.py            # yetishmayotgan kartalarni yasaydi
    python3 tools/cards.py --force    # hammasini qayta yasaydi
"""
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "tools", "fonts")
W = H = 1200
M = 88  # chetki bo'shliq

NAVY = (14, 40, 69)
NAVY_DARK = (8, 25, 46)
TEAL = (46, 170, 164)
GOLD = (214, 171, 90)
CREAM = (244, 237, 224)
MUTED = (182, 194, 210)


def font(name: str, size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(os.path.join(FONTS, name), size)
    try:
        axes = f.get_variation_axes()
        values = []
        for ax in axes:
            tag = ax.get("name", b"")
            tag = tag.decode() if isinstance(tag, bytes) else str(tag)
            if "eight" in tag or tag.lower() == "wght":
                values.append(weight)
            elif "ptical" in tag or tag.lower() == "opsz":
                values.append(min(max(size, ax["minimum"]), ax["maximum"]))
            else:
                values.append(ax["default"])
        f.set_variation_by_axes(values)
    except Exception:
        pass
    return f


def wrap(text: str, f: ImageFont.FreeTypeFont, width: int) -> list:
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if f.getlength(trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit(text: str, name: str, weight: int, start: int, minimum: int, width: int, max_lines: int):
    size = start
    while True:
        f = font(name, size, weight)
        lines = wrap(text, f, width)
        if len(lines) <= max_lines or size <= minimum:
            return f, lines, size
        size -= 3


def spaced(d, xy, text: str, f, fill, tracking: int) -> None:
    """Harflar orasi kengaytirilgan matn (kichik sarlavhalar uchun)."""
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + tracking


def background() -> Image.Image:
    # vertikal gradient (1 piksel kenglikda chizib, keyin cho'ziladi — tez)
    strip = Image.new("RGB", (1, H))
    for y in range(H):
        t = y / (H - 1)
        strip.putpixel((0, y), tuple(int(NAVY[i] * (1 - t) + NAVY_DARK[i] * t) for i in range(3)))
    img = strip.resize((W, H))
    # yumshoq ko'k-yashil nur (o'ng yuqori) va iliq nur (chap past)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse((760, -260, 1460, 440), fill=(18, 70, 80))
    g.ellipse((-320, 880, 380, 1580), fill=(60, 48, 20))
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    return ImageChops.add(img, glow)


def avatar(size: int):
    path = os.path.join(ROOT, "assets", "img", "avatar.jpg")
    if not os.path.exists(path):
        return None
    im = Image.open(path).convert("RGB").resize((size * 2, size * 2), Image.LANCZOS)
    mask = Image.new("L", (size * 2, size * 2), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 2 - 1, size * 2 - 1), fill=255)
    im.putalpha(mask)
    return im.resize((size, size), Image.LANCZOS)


def make_card(post: dict, site: dict, out_path: str) -> None:
    img = background()
    d = ImageDraw.Draw(img)
    frame_alpha = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(frame_alpha).rectangle((36, 36, W - 37, H - 37), outline=(255, 255, 255, 28), width=1)
    img = Image.alpha_composite(img.convert("RGBA"), frame_alpha)
    d = ImageDraw.Draw(img)

    # --- yuqori qism: avatar, ism, lavozim, raqam
    av = avatar(84)
    x = M
    if av:
        img.alpha_composite(av, (M, M - 6))
        x = M + 84 + 24
    d.text((x, M - 4), site["name"], font=font("Inter.ttf", 30, 650), fill=CREAM)
    d.text((x, M + 36), site["role"], font=font("Inter.ttf", 21, 450), fill=MUTED)
    num = f"№ {post['number']:02d}"
    nf = font("Inter.ttf", 26, 600)
    d.text((W - M - nf.getlength(num), M + 4), num, font=nf, fill=GOLD)

    # --- sarlavha va iqtibos
    width = W - 2 * M
    tf, tlines, tsize = fit(post["title"], "PlayfairDisplay.ttf", 700, 84, 50, width, 4)
    qf, qlines, qsize = fit("«" + post["quote"] + "»", "PlayfairDisplay-Italic.ttf", 400, 42, 30, width - 40, 6)
    t_lh = int(tsize * 1.12)
    q_lh = int(qsize * 1.38)
    label = (site.get("series") or "").upper()
    label_h = 56 if label else 0
    block = label_h + len(tlines) * t_lh + 58 + len(qlines) * q_lh
    top, bottom = 230, H - 170
    y = top + max(0, (bottom - top - block) // 2)

    # yarim shaffof bezak — katta qo'shtirnoq (alohida qatlamda, shaffoflik ishlashi uchun)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    big = font("PlayfairDisplay.ttf", 300, 700)
    ImageDraw.Draw(layer).text((W - M - 190, y - 150), "”", font=big, fill=(255, 255, 255, 22))
    img.alpha_composite(layer)
    d = ImageDraw.Draw(img)

    if label:
        spaced(d, (M, y), label, font("Inter.ttf", 20, 600), GOLD, 4)
        y += label_h
    for ln in tlines:
        d.text((M, y), ln, font=tf, fill=(255, 255, 255))
        y += t_lh
    y += 24
    d.rounded_rectangle((M, y, M + 72, y + 5), radius=3, fill=TEAL)
    y += 34
    for ln in qlines:
        d.text((M + 20, y), ln, font=qf, fill=CREAM)
        y += q_lh

    # --- pastki qism
    bf = font("Inter.ttf", 24, 550)
    handle = "t.me/" + site["telegram_channel"]
    d.text((M, H - M - 10), handle, font=bf, fill=GOLD)
    host = site["base_url"].split("//")[-1].rstrip("/")
    right = "" if "github.io" in host else host
    if not right and post["tags"]:
        right = post["tags"][-1]
    d.text((W - M - bf.getlength(right), H - M - 10), right, font=bf, fill=MUTED)

    rgb = img.convert("RGB")
    rgb.save(out_path, "JPEG", quality=90, optimize=True, progressive=True)
    # ro'yxat sahifalari uchun kichik nusxa
    rgb.resize((600, 600), Image.LANCZOS).save(out_path[:-4] + "-sm.jpg", "JPEG", quality=84, optimize=True)


def make_og(site: dict, out_path: str) -> None:
    """Bosh sahifa uchun 1200×630 ulashish rasmi."""
    global W, H
    W0, H0 = W, H
    W, H = 1200, 630
    try:
        img = background().convert("RGBA")
        d = ImageDraw.Draw(img)
        av = avatar(150)
        if av:
            img.alpha_composite(av, (M, 150))
        x = M + (190 if av else 0)
        label = (site.get("series") or "").upper()
        if label:
            spaced(d, (x, 150), label, font("Inter.ttf", 20, 600), GOLD, 4)
        d.text((x, 190), site["name"], font=font("PlayfairDisplay.ttf", 76, 700), fill=(255, 255, 255))
        d.text((x, 292), site["role"], font=font("Inter.ttf", 28, 450), fill=MUTED)
        d.rounded_rectangle((x, 350, x + 72, 355), radius=3, fill=TEAL)
        d.text((x, 380), site.get("tagline", ""), font=font("PlayfairDisplay-Italic.ttf", 34, 400), fill=CREAM)
        bf = font("Inter.ttf", 24, 550)
        d.text((M, H - M + 10), "t.me/" + site["telegram_channel"], font=bf, fill=GOLD)
        img.convert("RGB").save(out_path, "JPEG", quality=90, optimize=True, progressive=True)
    finally:
        W, H = W0, H0


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from build import load_posts, load_site  # noqa: E402

    site = load_site()
    force = "--force" in sys.argv
    os.makedirs(os.path.join(ROOT, "assets", "cards"), exist_ok=True)
    for p in load_posts():
        out = os.path.join(ROOT, "assets", "cards", p["slug"] + ".jpg")
        if force or not os.path.exists(out):
            make_card(p, site, out)
            print("karta:", p["slug"])
    og = os.path.join(ROOT, "assets", "img", "og.jpg")
    if force or not os.path.exists(og):
        make_og(site, og)
        print("og rasm yangilandi")
