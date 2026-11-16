"""Saytni quradi: posts/*.txt + data/published.json → HTML sahifalar.

    python3 tools/build.py          # faqat e'lon qilingan maqolalar (ishlab chiqarish)
    python3 tools/build.py --all    # hamma maqolalar (mahalliy ko'rib chiqish uchun)

Faqat Python standart kutubxonasi kerak (kartalar uchun esa Pillow — tools/cards.py).
"""
import glob
import html
import json
import os
import re
import shutil
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, "tools", "templates")
MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul",
          "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]


def load_site() -> dict:
    with open(os.path.join(ROOT, "data", "site.json"), encoding="utf-8") as f:
        return json.load(f)


def load_published() -> dict:
    path = os.path.join(ROOT, "data", "published.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_published(data: dict) -> None:
    with open(os.path.join(ROOT, "data", "published.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def parse_post(path: str) -> dict:
    """Fayl formati:  # Sarlavha / > Iqtibos / bo'sh qator / matn qatorlari / #teglar"""
    name = os.path.basename(path)[:-4]
    m = re.match(r"(\d+)-(.+)", name)
    number, slug = (int(m.group(1)), m.group(2)) if m else (0, name)
    lines = open(path, encoding="utf-8").read().replace("\r", "").split("\n")
    title, quote, body, tags = "", "", [], []
    for ln in lines:
        s = ln.rstrip()
        if not title and s.startswith("# "):
            title = s[2:].strip()
        elif not quote and s.startswith("> "):
            quote = s[2:].strip()
        elif s.startswith("#") and not s.startswith("# "):
            tags += [t for t in s.split() if t.startswith("#")]
        else:
            body.append(s)
    while body and not body[0]:
        body.pop(0)
    while body and not body[-1]:
        body.pop()
    if not title:
        sys.exit(f"{path}: birinchi qator '# Sarlavha' bo'lishi kerak")
    # birinchi mazmunli jumla — qisqa tavsif uchun
    excerpt = " ".join(l for l in body if l)[:200].rsplit(" ", 1)[0] + "…"
    return {"number": number, "slug": slug, "title": title, "quote": quote or title,
            "body": body, "tags": tags, "excerpt": excerpt, "file": path}


def load_posts() -> list:
    files = sorted(glob.glob(os.path.join(ROOT, "posts", "*.txt")))
    return [parse_post(p) for p in files]


# ---------- matn ko'rinishlari ----------

def telegram_text(post: dict, site: dict) -> str:
    body = "\n".join(post["body"])
    parts = [f"<b>{html.escape(post['title'].upper())}</b>", html.escape(body)]
    if post["tags"]:
        parts.append(" ".join(post["tags"]))
    if site.get("signature"):
        parts.append(html.escape(site["signature"]))
    return "\n\n".join(parts)


def plain_text(post: dict, site: dict) -> str:
    parts = [post["title"].upper(), "\n".join(post["body"])]
    if post["tags"]:
        parts.append(" ".join(post["tags"]))
    return "\n\n".join(parts)


# ---------- HTML ----------

def tpl(name: str) -> str:
    with open(os.path.join(TPL, name), encoding="utf-8") as f:
        return f.read()


def render(template: str, **ctx) -> str:
    out = template
    for k, v in ctx.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


def uz_date(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d}-{MONTHS[m - 1]}, {y}"


def body_html(post: dict) -> str:
    out = []
    for ln in post["body"]:
        if not ln:
            continue
        t = html.escape(ln)
        if ln.startswith("«") and ln.endswith("»"):
            out.append(f"<p class=\"said\">{t}</p>")
        else:
            out.append(f"<p>{t}</p>")
    return "\n".join(out)


def meta_label(post: dict) -> str:
    """'№ 02 · 16-noyabr, 2026' yoki raqamsiz postlar uchun faqat sana."""
    d = uz_date(post["date"])
    return f"№ {post['number']:02d} · {d}" if post["number"] else d


def card_html(post: dict, root: str) -> str:
    return render(tpl("card.html"), root=root, slug=post["slug"],
                  title=html.escape(post["title"]), excerpt=html.escape(post["excerpt"]),
                  meta=meta_label(post))


def page(layout: str, site: dict, root: str, path: str, title: str, description: str,
         image: str, content: str, extra_head: str = "", body_class: str = "") -> str:
    base = site["base_url"].rstrip("/")
    return render(layout, root=root, site_name=site["name"], role=site["role"],
                  title=html.escape(title), description=html.escape(description),
                  canonical=f"{base}/{path}", image=f"{base}/{image}",
                  channel=site["telegram_channel"], contact=site["telegram_contact"],
                  facebook=site.get("facebook_url", ""),
                  facebook_link=(f'<a href="{html.escape(site["facebook_url"])}" target="_blank" rel="noopener">Facebook</a>'
                                 if site.get("facebook_url") else ""),
                  year=date.today().year, content=content, extra_head=extra_head,
                  body_class=body_class)


def write(rel: str, text: str) -> None:
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def build_site(all_posts: bool = False) -> None:
    site = load_site()
    published = load_published()
    posts = load_posts()
    today = date.today().isoformat()
    for p in posts:
        info = published.get(p["slug"])
        p["date"] = info["date"] if info else today
        p["published"] = bool(info)
    visible = [p for p in posts if p["published"] or all_posts]
    visible.sort(key=lambda p: (p["date"], p["number"]), reverse=True)
    for i, p in enumerate(visible):
        p["newer"] = visible[i - 1] if i > 0 else None
        p["older"] = visible[i + 1] if i + 1 < len(visible) else None

    layout = tpl("layout.html")
    base = site["base_url"].rstrip("/")

    # bosh sahifa
    latest = "\n".join(card_html(p, "") for p in visible[:6])
    home = render(tpl("home.html"), site_name=site["name"], role=site["role"],
                  channel=site["telegram_channel"], contact=site["telegram_contact"],
                  facebook_btn=(f'<a class="btn btn-outline" href="{html.escape(site["facebook_url"])}" target="_blank" rel="noopener">Facebook</a>'
                                if site.get("facebook_url") else ""),
                  latest=latest or '<p class="muted">Maqolalar tez orada.</p>',
                  count=len(visible))
    write("index.html", page(layout, site, "", "", f"{site['name']} — {site['tagline']}",
                             site["description"], "assets/img/og.jpg", home, body_class="home"))

    # maqolalar ro'yxati
    cards = "\n".join(card_html(p, "../") for p in visible)
    lst = render(tpl("list.html"), cards=cards or '<p class="muted">Maqolalar tez orada.</p>', count=len(visible))
    write("maqolalar/index.html", page(layout, site, "../", "maqolalar/", f"Maqolalar — {site['name']}",
                                       "Ta’lim, rahbarlik, tarbiya va Registon tarixi haqida maqolalar.",
                                       "assets/img/og.jpg", lst))

    # alohida maqolalar
    keep = set()
    for p in visible:
        keep.add(p["slug"])
        nav = ""
        if p["older"]:
            nav += f'<a class="pn pn-prev" href="../{p["older"]["slug"]}/"><small>Oldingi</small>{html.escape(p["older"]["title"])}</a>'
        if p["newer"]:
            nav += f'<a class="pn pn-next" href="../{p["newer"]["slug"]}/"><small>Keyingi</small>{html.escape(p["newer"]["title"])}</a>'
        url = f"{base}/maqolalar/{p['slug']}/"
        art = render(tpl("article.html"), title=html.escape(p["title"]), quote=html.escape(p["quote"]),
                     meta=meta_label(p), body=body_html(p),
                     tags=" ".join(f'<span>{html.escape(t)}</span>' for t in p["tags"]),
                     slug=p["slug"], url=html.escape(url), url_q=html.escape(url, quote=True),
                     tg_share=f"https://t.me/share/url?url={url}&text={html.escape(p['title'])}",
                     fb_share=f"https://www.facebook.com/sharer/sharer.php?u={url}",
                     channel=site["telegram_channel"], site_name=site["name"], nav=nav)
        ld = json.dumps({"@context": "https://schema.org", "@type": "Article", "headline": p["title"],
                         "datePublished": p["date"], "author": {"@type": "Person", "name": site["name"]},
                         "image": f"{base}/assets/cards/{p['slug']}.jpg", "mainEntityOfPage": url,
                         "inLanguage": "uz"}, ensure_ascii=False)
        extra = f'<meta property="og:type" content="article"><meta property="article:published_time" content="{p["date"]}">' \
                f'<script type="application/ld+json">{ld}</script>'
        write(f"maqolalar/{p['slug']}/index.html",
              page(layout, site, "../../", f"maqolalar/{p['slug']}/", f"{p['title']} — {site['name']}",
                   p["quote"], f"assets/cards/{p['slug']}.jpg", art, extra_head=extra, body_class="article-page"))
    # e'lon qilinmagan (yoki o'chirilgan) maqola papkalarini tozalash
    for d in glob.glob(os.path.join(ROOT, "maqolalar", "*", "")):
        slug = os.path.basename(os.path.dirname(d))
        if slug not in keep:
            shutil.rmtree(d)

    # sitemap va robots
    urls = [f"{base}/", f"{base}/maqolalar/"] + [f"{base}/maqolalar/{p['slug']}/" for p in visible]
    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sm += "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n"
    write("sitemap.xml", sm)
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    print(f"Sayt qurildi: {len(visible)} ta maqola" + (" (hammasi, --all)" if all_posts else ""))


if __name__ == "__main__":
    build_site(all_posts="--all" in sys.argv)
