"""Kunlik nashr: navbatdagi maqolani saytga, Telegram kanalga va (sozlangan bo'lsa)
Facebook sahifaga joylaydi. GitHub Actions har kuni ishga tushiradi (.github/workflows/daily.yml).

Muhit o'zgaruvchilari:
  TELEGRAM_BOT_TOKEN   @BotFather bergan token (secret)
  TELEGRAM_CHAT_ID     kanal manzili, masalan @avazbek_tulovov
  FB_PAGE_ID           ixtiyoriy — Facebook sahifa ID'si
  FB_PAGE_TOKEN        ixtiyoriy — Facebook sahifa tokeni (secret)
  FORCE_SLUG           aynan shu maqolani hozir joylash: raqami (13) yoki papka nomi
  DRY_RUN=1            hech narsa yubormaydi va saqlamaydi, faqat nima bo'lishini ko'rsatadi
  PUSH=1               o'zgarishlarni git'ga commit + push qiladi (Actions'da yoqilgan)

Mantiq: bir kunda faqat bitta maqola. Avval o'tgan kunlarda yuborilmay qolganlar
(masalan, Telegram vaqtincha ishlamagan bo'lsa) qayta uriniladi, keyin navbatdagi eng kichik raqamli maqola olinadi.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # juda eski Python
    ZoneInfo = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import (ROOT, build_site, load_posts, load_published, load_site,  # noqa: E402
                   plain_text, save_published, telegram_text)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "").strip()
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "").strip()
FORCE = os.environ.get("FORCE_SLUG", "").strip()
DRY = os.environ.get("DRY_RUN", "").strip() not in ("", "0", "false")
PUSH = os.environ.get("PUSH", "").strip() not in ("", "0", "false")


def log(msg: str) -> None:
    print(msg, flush=True)


def today_in(tz: str) -> str:
    if ZoneInfo:
        return datetime.now(ZoneInfo(tz)).date().isoformat()
    return date.today().isoformat()


def git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def commit_push(message: str) -> None:
    if DRY or not PUSH:
        log(f"  (git: '{message}' — {'DRY_RUN' if DRY else 'PUSH yoqilmagan'}, o'tkazib yuborildi)")
        return
    git("add", "-A")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        log("  (git: o'zgarish yo'q)")
        return
    git("commit", "-m", message)
    git("push")
    log(f"  git: '{message}' push qilindi")


def wait_until_live(url: str, timeout: int = 720) -> bool:
    """GitHub Pages yangi faylni chiqarguncha kutadi (odatda 1–3 daqiqa)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{url}?v={int(time.time())}", headers={"User-Agent": "nashr-bot"})
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        log(f"  {url} hali ochilmadi, 20 soniya kutamiz…")
        time.sleep(20)
    return False


def api_post(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), headers={"User-Agent": "nashr-bot"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:400]}") from None


def send_telegram(post: dict, site: dict, image_url: str, article_url: str) -> int:
    payload = {
        "chat_id": CHAT_ID,
        "text": telegram_text(post, site),
        "parse_mode": "HTML",
        "link_preview_options": json.dumps({"url": image_url, "prefer_large_media": True, "show_above_text": True}),
        "reply_markup": json.dumps({"inline_keyboard": [[{"text": "Saytda o‘qish →", "url": article_url}]]}),
    }
    res = api_post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", payload)
    if not res.get("ok"):
        raise RuntimeError(f"Telegram: {res}")
    return res["result"]["message_id"]


def send_facebook(post: dict, site: dict, image_url: str, article_url: str) -> str:
    payload = {
        "url": image_url,
        "message": plain_text(post, site) + "\n\nTo‘liq o‘qish: " + article_url,
        "access_token": FB_PAGE_TOKEN,
    }
    res = api_post(f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/photos", payload)
    if "error" in res:
        raise RuntimeError(f"Facebook: {res['error'].get('message')}")
    return str(res.get("post_id") or res.get("id"))


def find_forced(posts: list, key: str):
    for p in posts:
        if key.isdigit() and p["number"] == int(key):
            return p
        if key in (p["slug"], f"{p['number']:02d}-{p['slug']}"):
            return p
    sys.exit(f"'{key}' nomli maqola topilmadi. posts/ papkasidagi fayl nomini yoki raqamini yozing.")


def choose(posts: list, published: dict, site: dict, today: str):
    """Qaysi maqola nashr qilinishini tanlaydi. (post, sabab) yoki (None, sabab)."""
    if FORCE:
        return find_forced(posts, FORCE), "qo'lda tanlandi"
    fb_on = bool(FB_PAGE_ID and FB_PAGE_TOKEN)
    for p in posts:
        e = published.get(p["slug"])
        if e and (not e.get("telegram") or (fb_on and not e.get("facebook"))):
            return p, f"{e['date']} kuni chala qolgan — qayta urinish"
    if site.get("paused"):
        return None, "site.json'da paused = true — nashr to'xtatilgan"
    if today < site.get("start_date", "2000-01-01"):
        return None, f"boshlanish sanasi {site['start_date']} hali kelmadi"
    if any(e.get("date") == today for e in published.values()):
        return None, "bugun maqola allaqachon chiqarilgan"
    pending = [p for p in posts if p["slug"] not in published]
    if not pending:
        return None, "navbat bo'sh — posts/ papkasiga yangi maqola qo'shing"
    return pending[0], "navbatdagi maqola"


def main() -> None:
    site = load_site()
    posts = load_posts()
    published = load_published()
    today = today_in(site.get("timezone", "Asia/Tashkent"))
    log(f"Sana: {today} ({site.get('timezone')}), e'lon qilingan: {len(published)}/{len(posts)}" + (" — DRY_RUN" if DRY else ""))

    if not DRY and not (TOKEN and CHAT_ID):
        log("Telegram sozlanmagan (TELEGRAM_BOT_TOKEN secret va TELEGRAM_CHAT_ID variable kerak). Hech narsa qilinmadi.")
        return

    post, why = choose(posts, published, site, today)
    if not post:
        log(f"Hech narsa qilinmadi: {why}")
        return
    log(f"Tanlandi: № {post['number']:02d} «{post['title']}» — {why}")

    # 1) Karta rasmi (yo'q bo'lsa yasaladi)
    card = os.path.join(ROOT, "assets", "cards", post["slug"] + ".jpg")
    if not os.path.exists(card):
        from cards import make_card, make_og
        make_card(post, site, card)
        og = os.path.join(ROOT, "assets", "img", "og.jpg")
        if not os.path.exists(og):
            make_og(site, og)
        log("  karta yasaldi")

    # 2) Saytga qo'shish va chiqarish
    entry = published.setdefault(post["slug"], {"date": today, "telegram": None, "facebook": None})
    if FORCE and entry.get("telegram"):
        log("  Diqqat: bu maqola avval yuborilgan, qayta yuboriladi")
        entry["telegram"] = None
        entry["facebook"] = None
    if DRY:
        log("  DRY_RUN: sayt qurilmaydi, published.json saqlanmaydi")
    else:
        save_published(published)
        build_site()
        commit_push(f"Yangi maqola: {post['title']}")

    base = site["base_url"].rstrip("/")
    image_url = f"{base}/assets/cards/{post['slug']}.jpg"
    article_url = f"{base}/maqolalar/{post['slug']}/"

    if DRY:
        log("\n--- Telegram matni ---\n" + telegram_text(post, site) + "\n--- tugadi ---")
        log(f"Rasm: {image_url}\nMaqola: {article_url}")
        log(f"Telegram: {'sozlangan' if TOKEN and CHAT_ID else 'TOKEN/CHAT_ID yo‘q'}; Facebook: {'sozlangan' if FB_PAGE_ID and FB_PAGE_TOKEN else 'sozlanmagan'}")
        return

    if PUSH:
        if not wait_until_live(image_url) or not wait_until_live(article_url):
            log("  Sayt o'z vaqtida ochilmadi; keyingi ishga tushishda qayta uriniladi")
            sys.exit(1)

    errors = []
    # 3) Telegram
    if TOKEN and CHAT_ID:
        if entry.get("telegram"):
            log("  Telegram: avval yuborilgan")
        else:
            try:
                entry["telegram"] = send_telegram(post, site, image_url, article_url)
                log(f"  ✅ Telegram: xabar #{entry['telegram']}")
            except Exception as e:  # noqa: BLE001
                errors.append(f"Telegram: {e}")
                log(f"  ❌ Telegram xatosi: {e}")
    else:
        log("  Telegram sozlanmagan (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")

    # 4) Facebook sahifa (ixtiyoriy)
    if FB_PAGE_ID and FB_PAGE_TOKEN:
        if entry.get("facebook"):
            log("  Facebook: avval yuborilgan")
        else:
            try:
                entry["facebook"] = send_facebook(post, site, image_url, article_url)
                log(f"  ✅ Facebook: post {entry['facebook']}")
            except Exception as e:  # noqa: BLE001
                errors.append(f"Facebook: {e}")
                log(f"  ❌ Facebook xatosi: {e}")

    save_published(published)
    commit_push(f"Nashr qilindi: {post['title']}")
    if errors:
        sys.exit("Xatolar: " + "; ".join(errors))
    log("Tayyor.")


if __name__ == "__main__":
    main()
