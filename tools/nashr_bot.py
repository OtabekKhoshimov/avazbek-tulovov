"""Nashr nazorati boti — serverda doim ishlaydi.

Nazorat guruhiga maqola namunasini tugmalar bilan yuboradi; «Tasdiqlash» bosilgandan keyingina
maqola saytga va Telegram kanalga chiqadi (tools/publish.py orqali).

Guruhdagi buyruqlar:
  /namuna [N]   — N-maqola (yoki navbatdagi) namunasini tugmalar bilan yuborish
  /holat        — nima chiqqan, nima navbatda, nima tasdiqlangan
  /pauza, /davom — kechki avtomatik namunani to'xtatish / davom ettirish

Serverda qo'lda:  python3 tools/nashr_bot.py preview [N]   (namuna yuborish)

.env (REPO_DIR/.. ichida):
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, REVIEW_GROUP_ID, REPO_DIR,
  PREVIEW_HOUR (18), PUBLISH_HOUR (9), TZ (Asia/Tashkent)
"""
import html
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(os.path.dirname(HERE))          # /opt/avazbek-nashr
ENV_FILE = os.path.join(BASE, ".env")


def load_env() -> None:
    if os.path.exists(ENV_FILE):
        for line in open(ENV_FILE, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GROUP = os.environ.get("REVIEW_GROUP_ID", "").strip()
REPO = os.environ.get("REPO_DIR", os.path.dirname(HERE)).rstrip("/")
TZ = ZoneInfo(os.environ.get("TZ", "Asia/Tashkent"))
PREVIEW_HOUR = int(os.environ.get("PREVIEW_HOUR", "18"))
PUBLISH_HOUR = int(os.environ.get("PUBLISH_HOUR", "9"))
STATE_FILE = os.path.join(BASE, "state.json")
PYTHON = sys.executable
GIT_ENV = {**os.environ, "HOME": BASE, "GIT_SSH_COMMAND": f"ssh -i {BASE}/.ssh/id_ed25519 -o UserKnownHostsFile={BASE}/.ssh/known_hosts -o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes"}

sys.path.insert(0, HERE)
from build import load_posts, load_published, load_site, telegram_text  # noqa: E402

LOCK = threading.Lock()


def log(*a) -> None:
    print(datetime.now(TZ).strftime("%H:%M:%S"), *a, flush=True)


# ---------- holat ----------

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"approved_morning": {}, "previews": {}, "paused": False, "last_preview_day": "", "last_publish_day": ""}


def save_state(st: dict) -> None:
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


# ---------- Telegram ----------

def tg(method: str, **params):
    data = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in params.items() if v is not None}
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data=urllib.parse.urlencode(data).encode())
    try:
        with urllib.request.urlopen(req, timeout=70) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        log(f"TG {method} HTTP {e.code}: {body[:300]}")
        return None
    except Exception as e:  # noqa: BLE001
        log(f"TG {method} xato: {e}")
        return None
    if not res.get("ok"):
        log(f"TG {method}: {res}")
        return None
    return res["result"]


def say(text: str, **kw):
    return tg("sendMessage", chat_id=GROUP, text=text, parse_mode="HTML", disable_web_page_preview=True, **kw)


# ---------- repo ----------

def run(cmd: list, env: dict = None, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO, env=env or GIT_ENV, capture_output=True, text=True, timeout=timeout)


def git_sync() -> None:
    run(["git", "fetch", "-q", "origin"])
    run(["git", "reset", "-q", "--hard", "origin/main"])


def find_post(key: str = ""):
    posts = load_posts()
    published = load_published()
    if key:
        for p in posts:
            if (key.isdigit() and p["number"] == int(key)) or key in (p["slug"], f"{p['number']:02d}-{p['slug']}"):
                return p
        return None
    pending = [p for p in posts if p["slug"] not in published]
    return pending[0] if pending else None


def is_published(slug: str) -> bool:
    e = load_published().get(slug)
    return bool(e and e.get("telegram"))


def wait_live(url: str, timeout: int = 600) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{url}?v={int(time.time())}", headers={"User-Agent": "nashr-bot"}), timeout=20) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(15)
    return False


def ensure_card_live(post: dict, site: dict) -> str:
    """Karta repo'da va saytda bo'lishini ta'minlaydi; rasm manzilini qaytaradi."""
    base = site["base_url"].rstrip("/")
    url = f"{base}/assets/cards/{post['slug']}.jpg"
    card = os.path.join(REPO, "assets", "cards", post["slug"] + ".jpg")
    photo_new = any(os.path.exists(os.path.join(REPO, "assets", "photos", post["slug"] + "." + e)) and
                    (not os.path.exists(card) or os.path.getmtime(os.path.join(REPO, "assets", "photos", post["slug"] + "." + e)) > os.path.getmtime(card))
                    for e in ("jpg", "jpeg", "png"))
    if not os.path.exists(card) or photo_new:
        run([PYTHON, "tools/cards.py"])
        run(["git", "add", "-A"])
        run(["git", "commit", "-q", "-m", f"Karta: {post['title']}"])
        run(["git", "push", "-q", "origin", "main"])
    wait_live(url, 600)
    return url


# ---------- namuna va tasdiqlash ----------

def send_preview(key: str = "", note: str = ""):
    with LOCK:
        git_sync()
        site = load_site()
        post = find_post(key)
        if not post:
            say("📭 Navbatda maqola yo‘q. <code>posts/</code> papkasiga yangi maqola qo‘shing." if not key else f"«{html.escape(key)}» topilmadi.")
            return
        if is_published(post["slug"]):
            say(f"№ {post['number']:02d} allaqachon kanalga chiqqan.")
            return
        image_url = ensure_card_live(post, site)
        article_url = f"{site['base_url'].rstrip('/')}/maqolalar/{post['slug']}/"
        header = f"<i>🔎 Namuna · № {post['number']:02d}. {note or 'Tasdiqlasangiz kanalga chiqadi.'}</i>"
        kb = {"inline_keyboard": [
            [{"text": "✅ Tasdiqlash — hozir chiqsin", "callback_data": f"now:{post['slug']}"}],
            [{"text": f"🕘 Tasdiqlash — ertaga {PUBLISH_HOUR:02d}:00 da", "callback_data": f"morning:{post['slug']}"}],
            [{"text": "✏️ Hali emas", "callback_data": f"later:{post['slug']}"}],
        ]}
        msg = tg("sendMessage", chat_id=GROUP, text=header + "\n\n" + telegram_text(post, site), parse_mode="HTML",
                 link_preview_options={"url": image_url, "prefer_large_media": True, "show_above_text": True},
                 reply_markup=kb)
        if msg:
            st = load_state()
            st["previews"][post["slug"]] = msg["message_id"]
            st["last_preview_day"] = datetime.now(TZ).date().isoformat()
            save_state(st)
            log("namuna yuborildi:", post["slug"])


def publish(slug: str, who: str = "") -> bool:
    """tools/publish.py ni ishga tushiradi: sayt + kanal. True — kanalga chiqdi."""
    with LOCK:
        git_sync()
        post = find_post(slug)
        if not post:
            say(f"«{html.escape(slug)}» topilmadi.")
            return False
        if is_published(slug):
            say(f"№ {post['number']:02d} allaqachon chiqqan.")
            return True
        status = say(f"⏳ № {post['number']:02d} chiqarilmoqda (sayt yangilanishi 1–3 daqiqa)…")
        env = {**GIT_ENV, "FORCE_SLUG": slug, "PUSH": "1", "TELEGRAM_BOT_TOKEN": TOKEN,
               "TELEGRAM_CHAT_ID": CHAT_ID, "REVIEW_GROUP_ID": ""}   # guruhga xabarni bot o'zi beradi
        r = run([PYTHON, "tools/publish.py"], env=env, timeout=1500)
        out = (r.stdout + r.stderr)[-1500:]
        log("publish:", r.returncode, out[-300:].replace("\n", " | "))
        git_sync()
        ok = is_published(slug)
        st = load_state()
        st["approved_morning"].pop(slug, None)
        save_state(st)
        if ok:
            mid = load_published()[slug]["telegram"]
            link = f"https://t.me/{CHAT_ID.lstrip('@')}/{mid}"
            text = f"✅ Kanalga chiqdi: № {post['number']:02d} «{html.escape(post['title'])}»" + (f"\nTasdiqladi: {html.escape(who)}" if who else "") + f"\n{link}"
        else:
            text = f"❌ № {post['number']:02d} chiqmadi.\n<pre>{html.escape(out[-700:])}</pre>"
        if status:
            tg("editMessageText", chat_id=GROUP, message_id=status["message_id"], text=text, parse_mode="HTML", disable_web_page_preview=True)
        else:
            say(text)
        return ok


def on_callback(cb: dict) -> None:
    data = cb.get("data", "")
    user = cb.get("from", {})
    who = (user.get("first_name", "") + " " + user.get("last_name", "")).strip()
    msg = cb.get("message", {})
    if str(msg.get("chat", {}).get("id")) != GROUP:
        tg("answerCallbackQuery", callback_query_id=cb["id"], text="Faqat nazorat guruhida ishlaydi")
        return
    action, _, slug = data.partition(":")
    post = find_post(slug)
    num = f"№ {post['number']:02d}" if post else slug
    if action == "now":
        tg("answerCallbackQuery", callback_query_id=cb["id"], text="Chiqarilmoqda…")
        tg("editMessageReplyMarkup", chat_id=GROUP, message_id=msg["message_id"],
           reply_markup={"inline_keyboard": [[{"text": f"✅ {who} tasdiqladi — chiqarilmoqda", "callback_data": "noop"}]]})
        threading.Thread(target=publish, args=(slug, who), daemon=True).start()
    elif action == "morning":
        st = load_state()
        st["approved_morning"][slug] = {"by": who, "at": datetime.now(TZ).isoformat()}
        save_state(st)
        tg("answerCallbackQuery", callback_query_id=cb["id"], text=f"Ertaga {PUBLISH_HOUR:02d}:00 da chiqadi")
        tg("editMessageReplyMarkup", chat_id=GROUP, message_id=msg["message_id"],
           reply_markup={"inline_keyboard": [[{"text": f"🕘 {who} tasdiqladi — ertaga {PUBLISH_HOUR:02d}:00 da chiqadi", "callback_data": "noop"}],
                                             [{"text": "✅ Hozir chiqsin", "callback_data": f"now:{slug}"}]]})
    elif action == "later":
        tg("answerCallbackQuery", callback_query_id=cb["id"], text="Kutiladi")
        tg("editMessageReplyMarkup", chat_id=GROUP, message_id=msg["message_id"],
           reply_markup={"inline_keyboard": [[{"text": "✏️ Kutilmoqda — tuzatish bo‘lsa shu yerga yozing", "callback_data": "noop"}],
                                             [{"text": "✅ Tasdiqlash — hozir chiqsin", "callback_data": f"now:{slug}"}]]})
        say(f"{num} kutib turibdi. Tuzatishdan keyin qayta namuna: <code>/namuna {post['number'] if post else ''}</code>")
    else:
        tg("answerCallbackQuery", callback_query_id=cb["id"])


def on_message(m: dict) -> None:
    if str(m.get("chat", {}).get("id")) != GROUP:
        return
    text = (m.get("text") or "").strip()
    if not text.startswith("/"):
        return
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lower()
    arg = arg.strip()
    if cmd == "/namuna":
        threading.Thread(target=send_preview, args=(arg,), daemon=True).start()
    elif cmd == "/holat":
        git_sync()
        posts, published, st = load_posts(), load_published(), load_state()
        pending = [p for p in posts if p["slug"] not in published]
        lines = [f"📊 Chiqqan: {len(published)} / {len(posts)}",
                 ("Navbatda: " + ", ".join("№%02d" % p["number"] for p in pending[:6]) + ("…" if len(pending) > 6 else "")) if pending else "Navbat bo‘sh"]
        if st["approved_morning"]:
            lines.append("Ertaga chiqadi: " + ", ".join(f"№{find_post(s)['number']:02d}" for s in st["approved_morning"] if find_post(s)))
        lines.append(f"Kechki namuna {PREVIEW_HOUR:02d}:00 — {'to‘xtatilgan' if st['paused'] else 'yoqilgan'}")
        say("\n".join(lines))
    elif cmd in ("/pauza", "/davom"):
        st = load_state()
        st["paused"] = cmd == "/pauza"
        save_state(st)
        say("⏸ Kechki avtomatik namuna to‘xtatildi. /namuna bilan qo‘lda yuborish mumkin." if st["paused"] else "▶️ Kechki avtomatik namuna yoqildi.")
    elif cmd in ("/start", "/help", "/yordam"):
        say("Buyruqlar: /namuna [N] — namuna yuborish, /holat — holat, /pauza, /davom")


# ---------- jadval ----------

def scheduler() -> None:
    while True:
        try:
            now = datetime.now(TZ)
            today = now.date().isoformat()
            st = load_state()
            if now.hour == PUBLISH_HOUR and st.get("last_publish_day") != today:
                st["last_publish_day"] = today
                save_state(st)
                for slug in list(st["approved_morning"].keys())[:1]:
                    publish(slug, st["approved_morning"][slug].get("by", ""))
            if now.hour == PREVIEW_HOUR and st.get("last_preview_day") != today and not st.get("paused"):
                st = load_state()
                st["last_preview_day"] = today
                save_state(st)
                if not st["approved_morning"]:
                    send_preview("", note=f"Ertangi maqola. Tasdiqlasangiz ertaga {PUBLISH_HOUR:02d}:00 da (yoki hozir) chiqadi.")
        except Exception:  # noqa: BLE001
            log("scheduler xato:\n" + traceback.format_exc())
        time.sleep(30)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "preview":
        send_preview(sys.argv[2] if len(sys.argv) > 2 else "")
        return
    if not (TOKEN and CHAT_ID and GROUP):
        sys.exit("TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, REVIEW_GROUP_ID kerak (.env)")
    me = tg("getMe")
    log("bot:", me and me.get("username"), "| repo:", REPO, "| guruh:", GROUP)
    tg("deleteWebhook")
    threading.Thread(target=scheduler, daemon=True).start()
    offset = 0
    while True:
        upd = tg("getUpdates", offset=offset, timeout=50, allowed_updates=["message", "callback_query"])
        if upd is None:
            time.sleep(5)
            continue
        for u in upd:
            offset = u["update_id"] + 1
            try:
                if "callback_query" in u:
                    on_callback(u["callback_query"])
                elif "message" in u:
                    on_message(u["message"])
            except Exception:  # noqa: BLE001
                log("update xato:\n" + traceback.format_exc())


if __name__ == "__main__":
    main()
