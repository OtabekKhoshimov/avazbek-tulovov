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
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, "tools", "templates")
MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul",
          "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]


def file_version(rel: str) -> str:
    """Fayl mazmunining qisqa xeshi — manzilga ?v= qo'shib, Telegram/brauzer keshini chetlab o'tamiz."""
    import hashlib
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return "0"
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:10]


def card_url(site: dict, slug: str) -> str:
    base = site["base_url"].rstrip("/")
    return f"{base}/assets/cards/{slug}.jpg?v={file_version(f'assets/cards/{slug}.jpg')}"


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
    excerpt = " ".join(BOLD.sub(r"\1", l) for l in body if l)[:200].rsplit(" ", 1)[0] + "…"
    quote = BOLD.sub(r"\1", quote)
    return {"number": number, "slug": slug, "title": title, "quote": quote or title,
            "body": body, "tags": tags, "excerpt": excerpt, "file": path}


def load_posts() -> list:
    files = sorted(glob.glob(os.path.join(ROOT, "posts", "*.txt")))
    return [parse_post(p) for p in files]


# ---------- matn ko'rinishlari ----------

BOLD = re.compile(r"\*\*(.+?)\*\*")


def rich(line: str) -> str:
    """**qalin** belgilarini Telegram/sayt HTML'iga aylantiradi (qolgani escape qilinadi)."""
    out, pos = [], 0
    for m in BOLD.finditer(line):
        out.append(html.escape(line[pos:m.start()]))
        out.append("<b>" + html.escape(m.group(1)) + "</b>")
        pos = m.end()
    out.append(html.escape(line[pos:]))
    return "".join(out)


def plain(line: str) -> str:
    return BOLD.sub(r"\1", line)


def telegram_text(post: dict, site: dict) -> str:
    body = "\n".join(rich(l) for l in post["body"])
    body = re.sub(r"\n{3,}", "\n\n", body)
    parts = [f"<b>{html.escape(post['title'].upper())}</b>", body]
    if post["tags"] and site.get("telegram_hashtags", False):
        parts.append(" ".join(post["tags"]))
    if site.get("signature"):
        parts.append(html.escape(site["signature"]))
    return "\n\n".join(parts)


def plain_text(post: dict, site: dict) -> str:
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(plain(l) for l in post["body"]))
    parts = [post["title"].upper(), body]
    if post["tags"] and site.get("telegram_hashtags", False):
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


LANGS = ["uz", "ru", "en"]
OG_LOCALE = {"uz": "uz_UZ", "ru": "ru_RU", "en": "en_US"}


def load_i18n() -> dict:
    with open(os.path.join(ROOT, "data", "i18n.json"), encoding="utf-8") as f:
        return json.load(f)


def lp(lang: str) -> str:
    """Til prefiksi: uz — ildiz, qolganlari /ru/, /en/."""
    return "" if lang == "uz" else lang + "/"


def uz_date(iso: str, lang: str = "uz", T: dict = None) -> str:
    T = T or load_i18n()[lang]
    y, m, d = (int(x) for x in iso.split("-"))
    return T["date_fmt"].format(d=d, m=T["months"][m - 1], y=y)


def translation(slug: str, lang: str):
    """posts/<lang>/<slug>.txt bo'lsa — tarjima (title, quote, body)."""
    if lang == "uz":
        return None
    path = os.path.join(ROOT, "posts", lang, slug + ".txt")
    if not os.path.exists(path):
        return None
    t = parse_post(path)
    return {"title": t["title"], "quote": t["quote"], "body": t["body"], "excerpt": t["excerpt"]}


def localized(post: dict, lang: str) -> dict:
    """Maqolaning berilgan tildagi ko'rinishi (tarjima bo'lmasa — o'zbekcha + belgi)."""
    tr = translation(post["slug"], lang)
    out = dict(post)
    out["translated"] = lang == "uz" or tr is not None
    if tr:
        out.update(tr)
    return out


def body_html(post: dict) -> str:
    """Bo'sh qator — yangi abzats; abzats ichidagi qatorlar <br> bilan ajratiladi."""
    paras, cur = [], []
    for ln in post["body"] + [""]:
        if ln:
            cur.append(ln)
        elif cur:
            paras.append(cur)
            cur = []
    out = []
    for lines in paras:
        if len(lines) == 1 and lines[0].startswith("«") and lines[0].endswith("»"):
            out.append(f"<p class=\"said\">{rich(lines[0])}</p>")
        else:
            out.append("<p>" + "<br>\n".join(rich(l) for l in lines) + "</p>")
    return "\n".join(out)


def meta_label(post: dict, lang: str, T: dict) -> str:
    d = uz_date(post["date"], lang, T)
    return f"№ {post['number']:02d} · {d}" if post["number"] else d


def card_html(post: dict, lang: str, T: dict, root: str, href: str) -> str:
    p = localized(post, lang)
    return render(tpl("card.html"), root=root, href=href, slug=p["slug"],
                  title=html.escape(p["title"]), excerpt=html.escape(p["excerpt"]), meta=meta_label(p, lang, T))


def tvars(T: dict) -> dict:
    return {"t_" + k: v for k, v in T.items() if isinstance(v, str)}


def page(layout: str, site: dict, lang: str, T: dict, depth: int, path: str, title: str, description: str,
         image: str, content: str, extra_head: str = "", body_class: str = "", langs=None) -> str:
    """path — tilsiz nisbiy manzil ('' , 'maqolalar/', 'maqolalar/slug/'). depth — sahifaning ildizdan chuqurligi."""
    base = site["base_url"].rstrip("/")
    root = "../" * depth
    langs = langs or LANGS
    alts = "".join(f'  <link rel="alternate" hreflang="{L}" href="{base}/{lp(L)}{path}">\n' for L in langs)
    alts += f'  <link rel="alternate" hreflang="x-default" href="{base}/{path}">'
    parts = []
    for L in langs:
        cls = ' class="active"' if L == lang else ""
        parts.append(f'<a href="{root}{lp(L)}{path}"{cls}>{L.upper()}</a>')
    switch = "".join(parts)
    fb = site.get("facebook_url", "")
    return render(layout, root=root, home=root + lp(lang), site_name=site["name"],
                  title=html.escape(title), description=html.escape(description),
                  canonical=f"{base}/{lp(lang)}{path}", image=f"{base}/{image}", alternates=alts, lang_switch=switch,
                  og_locale=OG_LOCALE[lang], channel=site["telegram_channel"], contact=site["telegram_contact"],
                  facebook_link=(f'<a href="{html.escape(fb)}" target="_blank" rel="noopener">Facebook</a>' if fb else ""),
                  year=date.today().year, content=content, extra_head=extra_head, body_class=body_class, **tvars(T))


def write(rel: str, text: str) -> None:
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def planned_dates(posts: list, site: dict, today: str) -> dict:
    """Navbatdagi maqolalar qaysi kuni chiqishi (kuniga bittadan, raqam tartibida)."""
    if site.get("paused"):
        return {}
    d = max(date.fromisoformat(site.get("start_date", today)), date.fromisoformat(today))
    if any(p["published"] and p["date"] == today for p in posts):
        d = max(d, date.fromisoformat(today) + timedelta(days=1))
    plan = {}
    for p in sorted((p for p in posts if not p["published"]), key=lambda x: x["number"]):
        plan[p["slug"]] = d.isoformat()
        d += timedelta(days=1)
    return plan


def build_site(all_posts: bool = False) -> None:
    site = load_site()
    published = load_published()
    posts = load_posts()
    i18n = load_i18n()
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
    fb = site.get("facebook_url", "")
    urls = []
    keep = set()

    for lang in LANGS:
        T = i18n[lang]
        pre = lp(lang)
        d0 = 1 if pre else 0          # bosh sahifa chuqurligi

        # --- bosh sahifa
        values = "\n".join(f'            <li><b>{html.escape(a)}</b><span>{html.escape(b)}</span></li>' for a, b in T["values"])
        timeline = "\n".join(f'          <li><span class="tl-year">{html.escape(y)}</span><div><b>{html.escape(t)}</b><p>{html.escape(x)}</p></div></li>'
                              for y, t, x in T["timeline"])
        latest = "\n".join(card_html(p, lang, T, "../" * d0, f"maqolalar/{p['slug']}/") for p in visible[:6])
        home = render(tpl("home.html"), root="../" * d0, channel=site["telegram_channel"], contact=site["telegram_contact"],
                      facebook_btn=(f'<a class="btn btn-outline" href="{html.escape(fb)}" target="_blank" rel="noopener">Facebook</a>' if fb else ""),
                      latest=latest or f'<p class="muted">{T["articles_soon"]}</p>', count=len(visible),
                      values=values, timeline=timeline, **tvars(T))
        write(f"{pre}index.html", page(layout, site, lang, T, d0, "", T["site_title"], T["site_description"],
                                       "assets/img/og.jpg", home, body_class="home"))
        urls.append(f"{base}/{pre}")

        # --- maqolalar ro'yxati
        cards = "\n".join(card_html(p, lang, T, "../" * (d0 + 1), f"{p['slug']}/") for p in visible)
        lst = render(tpl("list.html"), lead=T["list_lead"].format(n=len(visible)),
                     cards=cards or f'<p class="muted">{T["articles_soon"]}</p>', **tvars(T))
        write(f"{pre}maqolalar/index.html", page(layout, site, lang, T, d0 + 1, "maqolalar/",
                                                 f"{T['list_meta_title']} — {site['name']}", T["list_description"], "assets/img/og.jpg", lst))
        urls.append(f"{base}/{pre}maqolalar/")

        # --- alohida maqolalar
        for p in visible:
            keep.add(p["slug"])
            L = localized(p, lang)
            depth = d0 + 2
            root = "../" * depth
            nav = ""
            if p["older"]:
                o = localized(p["older"], lang)
                nav += f'<a class="pn pn-prev" href="../{o["slug"]}/"><small>{T["prev"]}</small>{html.escape(o["title"])}</a>'
            if p["newer"]:
                n = localized(p["newer"], lang)
                nav += f'<a class="pn pn-next" href="../{n["slug"]}/"><small>{T["next"]}</small>{html.escape(n["title"])}</a>'
            url = f"{base}/{pre}maqolalar/{p['slug']}/"
            notice = "" if L["translated"] else f'<p class="notice">{html.escape(T["untranslated"])}</p>'
            art = render(tpl("article.html"), root=root, title=html.escape(L["title"]), quote=html.escape(L["quote"]),
                         meta=meta_label(p, lang, T), body=body_html(L), notice=notice,
                         slug=p["slug"], url=html.escape(url), url_q=html.escape(url, quote=True),
                         tg_share=f"https://t.me/share/url?url={url}&text={html.escape(L['title'])}",
                         fb_share=f"https://www.facebook.com/sharer/sharer.php?u={url}",
                         channel=site["telegram_channel"], site_name=site["name"], nav=nav, **tvars(T))
            ld = json.dumps({"@context": "https://schema.org", "@type": "Article", "headline": L["title"],
                             "datePublished": p["date"], "author": {"@type": "Person", "name": site["name"]},
                             "image": f"{base}/assets/cards/{p['slug']}.jpg", "mainEntityOfPage": url,
                             "inLanguage": lang}, ensure_ascii=False)
            extra = f'<meta property="og:type" content="article"><meta property="article:published_time" content="{p["date"]}">' \
                    f'<script type="application/ld+json">{ld}</script>'
            write(f"{pre}maqolalar/{p['slug']}/index.html",
                  page(layout, site, lang, T, depth, f"maqolalar/{p['slug']}/", f"{L['title']} — {site['name']}",
                       L["quote"], f"assets/cards/{p['slug']}.jpg", art, extra_head=extra, body_class="article-page"))
            urls.append(url)

        # e'lon qilinmagan maqola papkalarini tozalash
        for d in glob.glob(os.path.join(ROOT, pre, "maqolalar", "*", "")):
            slug = os.path.basename(os.path.dirname(d))
            if slug not in keep:
                shutil.rmtree(d)

    # kartalar galereyasi — saytda ko'rinmaydi, faqat havola orqali
    T = i18n["uz"]
    plan = planned_dates(posts, site, today)
    items = []
    for p in sorted(posts, key=lambda x: x["number"]):
        if p["published"]:
            status = f"chiqqan: {uz_date(p['date'], 'uz', T)}"
        elif p["slug"] in plan:
            status = f"rejada: {uz_date(plan[p['slug']], 'uz', T)}"
        else:
            status = "navbatda"
        label = f"№ {p['number']:02d}" if p["number"] else "qo‘shimcha"
        items.append(f'<a class="card" href="../assets/cards/{p["slug"]}.jpg" target="_blank"><img src="../assets/cards/{p["slug"]}.jpg" alt="" loading="lazy" width="1200" height="1200">'
                     f'<div class="card-body"><small>{label} · {status}</small><h3>{html.escape(p["title"])}</h3></div></a>')
    gal = render(tpl("gallery.html"), items="\n".join(items), count=len(posts))
    write("kartalar/index.html", page(layout, site, "uz", T, 1, "kartalar/", f"Rasmlar — {site['name']}",
                                      "Maqolalar uchun tayyorlangan rasmlar", "assets/img/og.jpg", gal,
                                      extra_head='<meta name="robots" content="noindex, nofollow">', langs=["uz"]))

    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sm += "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n"
    write("sitemap.xml", sm)
    write("robots.txt", f"User-agent: *\nAllow: /\nDisallow: /kartalar/\nSitemap: {base}/sitemap.xml\n")
    print(f"Sayt qurildi: {len(visible)} ta maqola × {len(LANGS)} til" + (" (hammasi, --all)" if all_posts else ""))


if __name__ == "__main__":
    build_site(all_posts="--all" in sys.argv)
