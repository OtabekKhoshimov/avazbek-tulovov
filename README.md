# Avazbek Tulovov — shaxsiy sayt va kunlik nashr tizimi

Statik sayt (GitHub Pages) + har kuni bitta maqolani **Telegram kanalga** (va xohlasangiz **Facebook sahifaga**)
brendli rasm bilan avtomatik joylaydigan tizim.

## Qanday ishlaydi

1. Maqolalar `posts/` papkasida oddiy matn fayllar: `NN-nomi.txt` (NN — navbat raqami).
2. Har kuni **09:00** (Toshkent) GitHub Actions `tools/publish.py` ni ishga tushiradi:
   - navbatdagi (eng kichik raqamli, hali chiqmagan) maqolani oladi;
   - unga `assets/cards/` da 1200×1200 brendli rasm yasaydi (agar yo‘q bo‘lsa);
   - maqolani saytga qo‘shib, saytni qayta quradi va push qiladi;
   - sayt yangilangach, Telegram kanalga **katta rasm + to‘liq matn + «Saytda o‘qish»** tugmasi bilan yuboradi;
   - Facebook sahifa sozlangan bo‘lsa, o‘sha rasm va matnni u yerga ham joylaydi;
   - natijani `data/published.json` ga yozadi.
3. Bir kunda faqat bitta maqola chiqadi. Agar biror kuni Telegram ishlamay qolsa, ertasi kuni avval o‘sha maqola qayta yuboriladi.

## Maqola fayli formati

```
# Sarlavha (oddiy yozuvda; Telegram'da KATTA HARFLAR bilan chiqadi)
> Kartadagi iqtibos — matndan bitta kuchli jumla

Matn qatorlari...
Har bir qator — alohida abzats.

#Registon #Teglar
```

Yangi maqola qo‘shish: `posts/21-yangi-maqola.txt` faylini yarating va push qiling. Raqam navbatni belgilaydi.
Fayl nomida faqat lotin harflar, raqamlar va `-` ishlating.

## Sozlamalar (GitHub → Settings → Secrets and variables → Actions)

| Nomi | Turi | Nima |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | secret | @BotFather bergan token. Bot kanalda **admin** (xabar yuborish huquqi bilan) bo‘lishi kerak |
| `TELEGRAM_CHAT_ID` | variable | `@avazbek_tulovov` |
| `REVIEW_GROUP_ID` | variable | ixtiyoriy — nazorat guruhi ID'si: har kuni 18:00 da ertangi post namunasi, 09:00 da «kanalga chiqdi» xabari |
| `FB_PAGE_ID` | variable | ixtiyoriy — Facebook **sahifa** ID'si |
| `FB_PAGE_TOKEN` | secret | ixtiyoriy — sahifaning uzoq muddatli tokeni (`pages_manage_posts`, `pages_read_engagement`) |

Eslatma: Facebook API faqat **sahifalarga** (Page) joylashga ruxsat beradi, shaxsiy profilga emas.

Sayt sozlamalari — `data/site.json`: manzil (`base_url`), kanal, bog‘lanish, Facebook havolasi,
boshlanish sanasi (`start_date`), to‘xtatish (`paused: true`).

## Qo‘lda boshqarish

- **Hozir joylash:** Actions → «Kunlik nashr» → Run workflow → `slug` ga maqola raqamini yozing (masalan `13`).
- **Sinov:** o‘sha yerda `dry_run` ni belgilang — hech narsa yuborilmaydi, faqat log.
- **Pauza:** `data/site.json` da `"paused": true`.
- **Kartalarni qayta yasash** (dizayn yoki domen o‘zgarganda): Actions → «Saytni qayta qurish» → `force_cards`.

Mahalliy kompyuterda:

    python3 tools/cards.py            # yetishmayotgan kartalar
    python3 tools/build.py --all      # saytni hamma maqolalar bilan qurish (ko‘rib chiqish uchun)
    python3 tools/build.py            # faqat e'lon qilinganlar (ishlab chiqarish holati)
    DRY_RUN=1 python3 tools/publish.py

## Domen ulanganda

1. `data/site.json` da `base_url` ni `https://yangi-domen.uz` qiling.
2. Ildizga `CNAME` fayl qo‘ying (ichida faqat domen).
3. Actions → «Saytni qayta qurish» → `force_cards` bilan ishga tushiring (kartalardagi manzil yangilanadi).

## Papkalar

- `posts/` — maqolalar (manba). `data/published.json` — nima qachon chiqqani.
- `tools/` — `build.py` (sayt), `cards.py` (rasmlar), `publish.py` (nashr), `templates/` (HTML), `fonts/` (Playfair Display, Inter — OFL litsenziya).
- `assets/` — dizayn, rasmlar, kartalar. `maqolalar/` — qurilgan sahifalar (qo‘lda tahrirlanmaydi).
