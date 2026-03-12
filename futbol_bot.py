#!/usr/bin/env python3
"""
⚽ Futbol Tahmin & Analiz Telegram Botu v2
- Veri kaynağı: FBref (istatistik) + TheSportsDB (maçlar/skorlar)
- API key gerektirmez!
"""

import logging
import re
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
)

# ===================== AYARLAR =====================
TELEGRAM_TOKEN = "8610318322:AAFUcZ-pSbDIMiX_pK2t7mrWlJJQfdQLsrM"
BILDIRIM_SAATI = "08:00"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# FBref + TheSportsDB lig tanımları
LIGLER = {
    "🇹🇷 Süper Lig":      {"fbref": "https://fbref.com/en/comps/26/Super-Lig-Stats", "tsdb": "4967"},
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier Lig":    {"fbref": "https://fbref.com/en/comps/9/Premier-League-Stats", "tsdb": "4328"},
    "🇩🇪 Bundesliga":     {"fbref": "https://fbref.com/en/comps/20/Bundesliga-Stats", "tsdb": "4331"},
    "🇪🇸 La Liga":        {"fbref": "https://fbref.com/en/comps/12/La-Liga-Stats", "tsdb": "4335"},
    "🇮🇹 Serie A":        {"fbref": "https://fbref.com/en/comps/11/Serie-A-Stats", "tsdb": "4332"},
    "🇫🇷 Ligue 1":        {"fbref": "https://fbref.com/en/comps/13/Ligue-1-Stats", "tsdb": "4334"},
}

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# ===================== SCRAPER =====================
class FutbolScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get_soup(self, url: str) -> BeautifulSoup | None:
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"Scrape hatası {url}: {e}")
            return None

    def _tsdb_get(self, endpoint: str) -> dict:
        try:
            resp = self.session.get(f"https://www.thesportsdb.com/api/v1/json/3/{endpoint}", timeout=10)
            return resp.json()
        except Exception as e:
            logger.error(f"TSDB hatası: {e}")
            return {}

    def get_today_matches(self, tsdb_id: str) -> list:
        today = datetime.now().strftime("%Y-%m-%d")
        data = self._tsdb_get(f"eventsday.php?d={today}&s=Soccer")
        events = data.get("events") or []
        return [e for e in events if e.get("idLeague") == tsdb_id]

    def get_all_today_matches(self) -> list:
        today = datetime.now().strftime("%Y-%m-%d")
        data = self._tsdb_get(f"eventsday.php?d={today}&s=Soccer")
        events = data.get("events") or []
        tsdb_ids = {v["tsdb"] for v in LIGLER.values()}
        return [e for e in events if e.get("idLeague") in tsdb_ids]

    def get_league_table(self, tsdb_id: str) -> list:
        data = self._tsdb_get(f"lookuptable.php?l={tsdb_id}&s=2024-2025")
        return data.get("table") or []

    def get_fbref_stats(self, fbref_url: str) -> list:
        soup = self._get_soup(fbref_url)
        if not soup:
            return []
        try:
            table = soup.find("table", {"id": re.compile(r"results.*overall|stats_squads_standard_for")})
            if not table:
                tables = soup.find_all("table", class_="stats_table")
                table = tables[0] if tables else None
            if not table:
                return []
            rows = []
            for tr in table.find("tbody").find_all("tr"):
                if "thead" in tr.get("class", []) or "spacer" in tr.get("class", []):
                    continue
                tds = {td.get("data-stat"): td.get_text(strip=True) for td in tr.find_all(["td", "th"])}
                if tds.get("team"):
                    rows.append(tds)
            return rows
        except Exception as e:
            logger.error(f"FBref stats hatası: {e}")
            return []

    def get_fbref_fixtures(self, fbref_url: str) -> list:
        fixtures_url = fbref_url.replace("-Stats", "-fixtures")
        soup = self._get_soup(fixtures_url)
        if not soup:
            return []
        try:
            table = soup.find("table", id=re.compile(r"sched"))
            if not table:
                return []
            today = datetime.now().date()
            maclar = []
            for tr in table.find("tbody").find_all("tr"):
                if "spacer" in tr.get("class", []) or "thead" in tr.get("class", []):
                    continue
                tds = {td.get("data-stat"): td.get_text(strip=True) for td in tr.find_all(["td", "th"])}
                try:
                    tarih = datetime.strptime(tds.get("date", ""), "%Y-%m-%d").date()
                    if tarih == today:
                        maclar.append({
                            "time": tds.get("time", "?"),
                            "home": tds.get("home_team", "?"),
                            "score": tds.get("score", "vs"),
                            "away": tds.get("away_team", "?"),
                        })
                except:
                    continue
            return maclar
        except Exception as e:
            logger.error(f"FBref fixtures hatası: {e}")
            return []


# ===================== TAHMİN =====================
class TahminMotoru:
    @staticmethod
    def tahmin_et(ev_row: dict, dep_row: dict) -> tuple:
        try:
            def puan_hesapla(row):
                g = float(row.get("wins", 0) or 0)
                b = float(row.get("draws", 0) or 0)
                m = float(row.get("losses", 0) or 0)
                top = g + b + m
                return (g * 3 + b) / max(top * 3, 1) * 100

            ev_p = puan_hesapla(ev_row) + 10
            dep_p = puan_hesapla(dep_row)

            # xG bonusu
            try:
                ev_xg = float(ev_row.get("xg", 0) or 0)
                dep_xg = float(dep_row.get("xg", 0) or 0)
                if ev_xg > 0:
                    ev_p = (ev_p + ev_xg * 8) / 2
                if dep_xg > 0:
                    dep_p = (dep_p + dep_xg * 8) / 2
            except:
                pass

            fark = ev_p - dep_p
            if fark > 15:
                return "🏠 Ev Sahibi Kazanır", min(82, 60 + int(fark / 2))
            elif fark < -15:
                return "✈️ Deplasman Kazanır", min(80, 60 + int(abs(fark) / 2))
            else:
                return "🤝 Beraberlik / Her İkisi", 52
        except:
            return "❓ Yeterli veri yok", 0


# ===================== FORMAT =====================
def format_events(events: list, lig_adi: str = "") -> str:
    if not events:
        return f"📭 {'Bugün' if not lig_adi else lig_adi} için maç bulunamadı."
    baslik = f"⚽ *{lig_adi} MAÇLARI*" if lig_adi else "⚽ *BUGÜNÜN MAÇLARI*"
    mesaj = f"{baslik} ({datetime.now().strftime('%d.%m.%Y')})\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for e in events[:15]:
        ev = e.get("strHomeTeam", "?")
        dep = e.get("strAwayTeam", "?")
        ev_gol = e.get("intHomeScore")
        dep_gol = e.get("intAwayScore")
        saat = e.get("strTime", "?")
        durum = e.get("strStatus", "")
        try:
            t = datetime.strptime(saat[:5], "%H:%M") + timedelta(hours=3)
            saat = t.strftime("%H:%M")
        except:
            pass
        if ev_gol is not None and dep_gol is not None:
            emoji = "🔴" if durum in ["1H","2H","HT","ET"] else "✅"
            mesaj += f"{emoji} *{ev}* {ev_gol}-{dep_gol} *{dep}*\n"
        else:
            mesaj += f"🕐 {saat} | *{ev}* vs *{dep}*\n"
    return mesaj


def format_table(tablo: list, lig_adi: str) -> str:
    if not tablo:
        return "❌ Puan durumu alınamadı."
    mesaj = f"📊 *{lig_adi} PUAN DURUMU*\n━━━━━━━━━━━━━━━━━━━━━━\n"
    mesaj += "`#   Takım            O   G   B   M   P`\n"
    for i, s in enumerate(tablo[:10], 1):
        takim = s.get("strTeam", "?")[:13].ljust(13)
        o = str(s.get("intPlayed", "?")).rjust(2)
        g = str(s.get("intWin", "?")).rjust(2)
        b = str(s.get("intDraw", "?")).rjust(2)
        m = str(s.get("intLoss", "?")).rjust(2)
        p = str(s.get("intPoints", "?")).rjust(3)
        emoji = "🏆" if i <= 4 else ("🔴" if i >= 9 else "  ")
        mesaj += f"`{str(i).rjust(2)} {emoji}{takim} {o} {g} {b} {m} {p}`\n"
    return mesaj


# ===================== BOT =====================
scraper = FutbolScraper()
tahmin_motoru = TahminMotoru()
bildirim_listesi: set = set()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ *FUTBOL ANALİZ BOTUNA HOŞGELDİN!*\n\n"
        "📌 *Komutlar:*\n\n"
        "🗓 /bugun - Bugünün maçları\n"
        "🔴 /canli - Canlı & son maçlar\n"
        "📊 /puan - Puan durumu\n"
        "🎯 /tahmin - Maç tahminleri\n"
        "📈 /istatistik - Takım istatistikleri\n"
        "🔔 /bildirim - Günlük bildirim aç/kapat\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Veri: FBref & TheSportsDB",
        parse_mode="Markdown"
    )


async def bugun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"bugun|{a}")] for a in LIGLER]
    keyboard.append([InlineKeyboardButton("🌍 Tüm Ligler", callback_data="bugun|TUM")])
    await update.message.reply_text(
        "🗓 *Hangi ligin maçlarını görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def canli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Yükleniyor...")
    events = scraper.get_all_today_matches()
    oynanan = [e for e in events if e.get("intHomeScore") is not None]
    if not oynanan:
        await update.message.reply_text("📭 Şu an canlı/bitmiş maç bulunamadı.")
        return
    mesaj = f"🔴 *CANLI & SON MAÇLAR*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for e in oynanan[:12]:
        lig = e.get("strLeague", "?")
        ev = e.get("strHomeTeam", "?")
        dep = e.get("strAwayTeam", "?")
        ev_g = e.get("intHomeScore", "?")
        dep_g = e.get("intAwayScore", "?")
        durum = e.get("strStatus", "")
        emoji = "🔴" if durum in ["1H","2H","HT"] else "✅"
        mesaj += f"{emoji} _{lig}_\n*{ev}* {ev_g}-{dep_g} *{dep}*\n\n"
    await update.message.reply_text(mesaj, parse_mode="Markdown")


async def puan_durumu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"puan|{a}")] for a in LIGLER]
    await update.message.reply_text(
        "📊 *Hangi ligin puan durumunu görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def tahmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"tahmin|{a}")] for a in LIGLER]
    await update.message.reply_text(
        "🎯 *Hangi lig için tahmin almak istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def istatistik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"istat|{a}")] for a in LIGLER]
    await update.message.reply_text(
        "📈 *Hangi ligin istatistiklerini görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def bildirim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in bildirim_listesi:
        bildirim_listesi.remove(user_id)
        await update.message.reply_text("🔕 Bildirimler *kapatıldı*.", parse_mode="Markdown")
    else:
        bildirim_listesi.add(user_id)
        await update.message.reply_text(
            f"🔔 Bildirimler *açıldı!* Her gün {BILDIRIM_SAATI}'de özet gelecek.",
            parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    islem, lig_adi = query.data.split("|", 1)
    lig_info = LIGLER.get(lig_adi, {})

    if islem == "bugun":
        await query.edit_message_text("⏳ Maçlar yükleniyor...")
        if lig_adi == "TUM":
            events = scraper.get_all_today_matches()
            await query.edit_message_text(format_events(events), parse_mode="Markdown")
        else:
            events = scraper.get_today_matches(lig_info.get("tsdb", ""))
            await query.edit_message_text(format_events(events, lig_adi), parse_mode="Markdown")

    elif islem == "puan":
        await query.edit_message_text("⏳ Puan durumu yükleniyor...")
        tablo = scraper.get_league_table(lig_info.get("tsdb", ""))
        await query.edit_message_text(format_table(tablo, lig_adi), parse_mode="Markdown")

    elif islem == "tahmin":
        await query.edit_message_text("⏳ Tahminler hazırlanıyor...")
        events = scraper.get_today_matches(lig_info.get("tsdb", ""))
        stats = scraper.get_fbref_stats(lig_info.get("fbref", ""))
        stats_dict = {row.get("team", "").lower(): row for row in stats}

        if not events:
            await query.edit_message_text(f"📭 {lig_adi} için bugün maç yok.")
            return

        mesaj = f"🎯 *{lig_adi} TAHMİNLERİ*\n📅 {datetime.now().strftime('%d.%m.%Y')}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for e in events[:5]:
            ev_adi = e.get("strHomeTeam", "?")
            dep_adi = e.get("strAwayTeam", "?")
            saat = e.get("strTime", "?")
            try:
                t = datetime.strptime(saat[:5], "%H:%M") + timedelta(hours=3)
                saat = t.strftime("%H:%M")
            except:
                pass

            ev_stats = stats_dict.get(ev_adi.lower(), {})
            dep_stats = stats_dict.get(dep_adi.lower(), {})
            tahmin_sonuc, guven = tahmin_motoru.tahmin_et(ev_stats, dep_stats)
            cubuk = "█" * int(guven/10) + "░" * (10 - int(guven/10))

            mesaj += f"⚔️ *{ev_adi}* vs *{dep_adi}*\n"
            mesaj += f"   🕐 {saat}\n"
            if ev_stats:
                mesaj += f"   🏠 {ev_stats.get('wins','?')}G {ev_stats.get('draws','?')}B {ev_stats.get('losses','?')}M xG:{ev_stats.get('xg','?')}\n"
            if dep_stats:
                mesaj += f"   ✈️ {dep_stats.get('wins','?')}G {dep_stats.get('draws','?')}B {dep_stats.get('losses','?')}M xG:{dep_stats.get('xg','?')}\n"
            if guven > 0:
                mesaj += f"   💡 {tahmin_sonuc}\n   📈 [{cubuk}] %{guven}\n"
            mesaj += "\n"

        mesaj += "⚠️ _FBref istatistiklerine dayanır._"
        await query.edit_message_text(mesaj, parse_mode="Markdown")

    elif islem == "istat":
        await query.edit_message_text("⏳ İstatistikler yükleniyor...")
        tablo = scraper.get_league_table(lig_info.get("tsdb", ""))
        if not tablo:
            await query.edit_message_text("❌ İstatistik alınamadı.")
            return
        mesaj = f"📈 *{lig_adi} TAKIM İSTATİSTİKLERİ*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for s in tablo[:8]:
            gf = s.get("intGoalsFor", "?")
            ga = s.get("intGoalsAgainst", "?")
            mesaj += f"🔵 *{s.get('strTeam','?')}*\n"
            mesaj += f"   {s.get('intWin','?')}G {s.get('intDraw','?')}B {s.get('intLoss','?')}M | Gol: {gf}/{ga}\n\n"
        await query.edit_message_text(mesaj, parse_mode="Markdown")


async def gunluk_bildirim_gonder(context: ContextTypes.DEFAULT_TYPE):
    if not bildirim_listesi:
        return
    events = scraper.get_all_today_matches()
    mesaj = f"🌅 *GÜNLÜK FUTBOL BÜLTENİ*\n{datetime.now().strftime('%d.%m.%Y')}\n\n"
    mesaj += format_events(events[:10])
    for user_id in bildirim_listesi.copy():
        try:
            await context.bot.send_message(chat_id=user_id, text=mesaj, parse_mode="Markdown")
        except Exception as e:
            bildirim_listesi.discard(user_id)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bugun", bugun))
    app.add_handler(CommandHandler("canli", canli))
    app.add_handler(CommandHandler("puan", puan_durumu))
    app.add_handler(CommandHandler("tahmin", tahmin))
    app.add_handler(CommandHandler("istatistik", istatistik))
    app.add_handler(CommandHandler("bildirim", bildirim))
    app.add_handler(CallbackQueryHandler(button_handler))
    saat, dakika = map(int, BILDIRIM_SAATI.split(":"))
    app.job_queue.run_daily(
        gunluk_bildirim_gonder,
        time=datetime.now().replace(hour=saat, minute=dakika, second=0).time()
    )
    logger.info("⚽ Futbol Bot v2 başlatıldı!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
