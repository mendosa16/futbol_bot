#!/usr/bin/env python3
"""
⚽ Futbol Tahmin Telegram Botu
- api-football.com direkt API kullanır
- 900+ lig (Süper Lig dahil)
- Günlük maç tahminleri, istatistik analizi
- Canlı skor takibi
- Otomatik günlük bildirim
"""

import os
import logging
from datetime import datetime, timedelta
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ===================== AYARLAR =====================
TELEGRAM_TOKEN = "8610318322:AAFUcZ-pSbDIMiX_pK2t7mrWlJJQfdQLsrM"
FOOTBALL_API_KEY = "1fdfe32100d5b7c9be44d36e89c6c21e"
BILDIRIM_SAATI = "08:00"

LIGLER = {
    "🇹🇷 Süper Lig": 203,
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier Lig": 39,
    "🇩🇪 Bundesliga": 78,
    "🇪🇸 La Liga": 140,
    "🇮🇹 Serie A": 135,
    "🇫🇷 Ligue 1": 61,
    "🏆 Şampiyonlar Ligi": 2,
    "🌍 Avrupa Ligi": 3,
    "🇳🇱 Eredivisie": 88,
    "🇵🇹 Primeira Liga": 94,
}

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# ===================== API SINIFI =====================
class FootballAPI:
    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key: str):
        self.headers = {
            "x-apisports-key": api_key
        }

    def get_fixtures(self, tarih: str = None, lig_id: int = None) -> list:
        if tarih is None:
            tarih = datetime.now().strftime("%Y-%m-%d")
        params = {"date": tarih, "timezone": "Europe/Istanbul"}
        if lig_id:
            params["league"] = lig_id
            params["season"] = datetime.now().year
        try:
            resp = requests.get(f"{self.BASE_URL}/fixtures", headers=self.headers, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json().get("response", [])
        except Exception as e:
            logger.error(f"Fixtures hatası: {e}")
            return []

    def get_standings(self, lig_id: int) -> list:
        params = {"league": lig_id, "season": datetime.now().year}
        try:
            resp = requests.get(f"{self.BASE_URL}/standings", headers=self.headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json().get("response", [])
            if data:
                return data[0].get("league", {}).get("standings", [[]])[0]
            return []
        except Exception as e:
            logger.error(f"Standings hatası: {e}")
            return []

    def get_team_stats(self, takim_id: int, lig_id: int) -> dict:
        params = {"team": takim_id, "league": lig_id, "season": datetime.now().year}
        try:
            resp = requests.get(f"{self.BASE_URL}/teams/statistics", headers=self.headers, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json().get("response", {})
        except Exception as e:
            logger.error(f"Team stats hatası: {e}")
            return {}

    def get_predictions(self, fixture_id: int) -> dict:
        params = {"fixture": fixture_id}
        try:
            resp = requests.get(f"{self.BASE_URL}/predictions", headers=self.headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json().get("response", [])
            return data[0] if data else {}
        except Exception as e:
            logger.error(f"Predictions hatası: {e}")
            return {}

    def get_live_fixtures(self) -> list:
        params = {"live": "all"}
        try:
            resp = requests.get(f"{self.BASE_URL}/fixtures", headers=self.headers, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json().get("response", [])
        except Exception as e:
            logger.error(f"Live fixtures hatası: {e}")
            return []


# ===================== TAHMİN MOTORU =====================
class TahminMotoru:

    @staticmethod
    def analiz_et(stats: dict) -> dict:
        if not stats:
            return {"form_puani": 50, "gol_ort": 1.0, "form_str": "?????"}
        form = stats.get("form", "") or ""
        form_puani = sum(3 if c == "W" else 1 if c == "D" else 0 for c in form[-5:])
        form_yuzdesi = (form_puani / 15) * 100
        gol_data = stats.get("goals", {}).get("for", {}).get("average", {})
        gol_ort = float(gol_data.get("total", 1.0) or 1.0)
        return {"form_puani": round(form_yuzdesi, 1), "gol_ort": gol_ort, "form_str": form[-5:] if form else "?????"}

    @staticmethod
    def tahmin_uret(ev_stats: dict, dep_stats: dict, prediction: dict = None) -> tuple:
        if prediction:
            percent = prediction.get("predictions", {}).get("percent", {})
            if percent:
                ev_y = int(percent.get("home", "0").replace("%", "") or 0)
                dep_y = int(percent.get("away", "0").replace("%", "") or 0)
                ber_y = int(percent.get("draws", "0").replace("%", "") or 0)
                if ev_y >= dep_y and ev_y >= ber_y:
                    return "🏠 Ev Sahibi Kazanır", ev_y
                elif dep_y >= ev_y and dep_y >= ber_y:
                    return "✈️ Deplasman Kazanır", dep_y
                else:
                    return "🤝 Beraberlik", ber_y
        ev_puan = ev_stats.get("form_puani", 50) + 10
        dep_puan = dep_stats.get("form_puani", 50)
        fark = ev_puan - dep_puan
        if fark > 20:
            return "🏠 Ev Sahibi Kazanır", min(80, 60 + int(fark / 2))
        elif fark < -20:
            return "✈️ Deplasman Kazanır", min(80, 60 + int(abs(fark) / 2))
        else:
            return "🤝 Beraberlik / Her İkisi", 50


# ===================== FORMAT =====================
def format_mac_listesi(maclar: list, lig_adi: str = "") -> str:
    if not maclar:
        return "📭 Bugün için maç bulunamadı."
    baslik = f"⚽ *{lig_adi} MAÇLARI*" if lig_adi else "⚽ *BUGÜNÜN MAÇLARI*"
    mesaj = f"{baslik} ({datetime.now().strftime('%d.%m.%Y')})\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for mac in maclar[:15]:
        fixture = mac.get("fixture", {})
        teams = mac.get("teams", {})
        goals = mac.get("goals", {})
        status = fixture.get("status", {}).get("short", "")
        ev = teams.get("home", {}).get("name", "?")
        dep = teams.get("away", {}).get("name", "?")
        try:
            mac_dt = datetime.fromisoformat(fixture.get("date", "").replace("Z", "+00:00"))
            mac_dt = mac_dt + timedelta(hours=3)
            saat = mac_dt.strftime("%H:%M")
        except:
            saat = "?"
        if status == "FT":
            mesaj += f"✅ {ev} *{goals.get('home','-')}-{goals.get('away','-')}* {dep}\n"
        elif status in ["1H", "2H", "HT"]:
            dakika = fixture.get("status", {}).get("elapsed", "?")
            mesaj += f"🔴 {dakika}' | {ev} *{goals.get('home',0)}-{goals.get('away',0)}* {dep}\n"
        else:
            mesaj += f"🕐 {saat} | {ev} vs {dep}\n"
    return mesaj


def format_puan_durumu(tablo: list, lig_adi: str) -> str:
    if not tablo:
        return "❌ Puan durumu alınamadı."
    mesaj = f"📊 *{lig_adi} PUAN DURUMU*\n━━━━━━━━━━━━━━━━━━━━━━\n"
    mesaj += "`#   Takım            O   G   B   M   P`\n"
    for satir in tablo[:10]:
        pos = satir.get("rank", "?")
        takim = satir.get("team", {}).get("name", "?")[:13].ljust(13)
        a = satir.get("all", {})
        o, g, b, m, p = a.get("played",0), a.get("win",0), a.get("draw",0), a.get("lose",0), satir.get("points",0)
        emoji = "🏆" if pos <= 4 else ("🔴" if pos >= len(tablo) - 2 else "  ")
        mesaj += f"`{str(pos).rjust(2)} {emoji}{takim} {str(o).rjust(2)} {str(g).rjust(2)} {str(b).rjust(2)} {str(m).rjust(2)} {str(p).rjust(3)}`\n"
    return mesaj


# ===================== KOMUTLAR =====================
api = FootballAPI(FOOTBALL_API_KEY)
tahmin_motoru = TahminMotoru()
bildirim_listesi: set = set()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mesaj = (
        "⚽ *FUTBOL TAHMİN BOTUNA HOŞGELDİN!*\n\n"
        "📌 *Komutlar:*\n\n"
        "🗓 /bugun - Bugünün maçları\n"
        "🔴 /canli - Canlı maçlar\n"
        "📊 /puan - Puan durumu\n"
        "🎯 /tahmin - Maç tahminleri\n"
        "🔔 /bildirim - Günlük bildirim aç/kapat\n"
        "ℹ️ /hakkinda - Bot hakkında\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Her gün 08:00'de otomatik maç özeti!"
    )
    await update.message.reply_text(mesaj, parse_mode="Markdown")


async def bugun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"bugun_{i}_{a}")] for a, i in LIGLER.items()]
    keyboard.append([InlineKeyboardButton("🌍 Tüm Maçlar", callback_data="bugun_0_Tüm Maçlar")])
    await update.message.reply_text("🗓 *Hangi ligin maçlarını görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def canli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Canlı maçlar yükleniyor...")
    maclar = api.get_live_fixtures()
    if not maclar:
        await update.message.reply_text("📭 Şu an canlı maç yok.")
        return
    mesaj = f"🔴 *CANLI MAÇLAR* ({len(maclar)} maç)\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for mac in maclar[:10]:
        teams = mac.get("teams", {})
        goals = mac.get("goals", {})
        fixture = mac.get("fixture", {})
        lig = mac.get("league", {}).get("name", "")
        dakika = fixture.get("status", {}).get("elapsed", "?")
        ev = teams.get("home", {}).get("name", "?")
        dep = teams.get("away", {}).get("name", "?")
        mesaj += f"⚽ *{lig}*\n🔴 {dakika}' | {ev} *{goals.get('home',0)}-{goals.get('away',0)}* {dep}\n\n"
    await update.message.reply_text(mesaj, parse_mode="Markdown")


async def puan_durumu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"puan_{i}_{a}")] for a, i in LIGLER.items()]
    await update.message.reply_text("📊 *Hangi ligin puan durumunu görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def tahmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"tahmin_{i}_{a}")] for a, i in LIGLER.items()]
    await update.message.reply_text("🎯 *Hangi lig için tahmin almak istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def bildirim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in bildirim_listesi:
        bildirim_listesi.remove(user_id)
        await update.message.reply_text("🔕 Günlük bildirimler *kapatıldı*.", parse_mode="Markdown")
    else:
        bildirim_listesi.add(user_id)
        await update.message.reply_text(
            f"🔔 Günlük bildirimler *açıldı!*\nHer gün {BILDIRIM_SAATI}'de özet gelecek.",
            parse_mode="Markdown")


async def hakkinda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *FUTBOL TAHMİN BOTU*\n\n"
        "📡 api-football.com (900+ lig)\n"
        "🤖 AI destekli tahmin motoru\n"
        "🔴 Canlı skor takibi\n"
        "📊 Detaylı istatistikler\n\n"
        "⚠️ Tahminler istatistiksel analize dayanır.",
        parse_mode="Markdown"
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    islem, lig_id, lig_adi = parts[0], int(parts[1]), parts[2] if len(parts) > 2 else ""

    if islem == "bugun":
        await query.edit_message_text("⏳ Maçlar yükleniyor...")
        maclar = api.get_fixtures(lig_id=lig_id if lig_id else None)
        await query.edit_message_text(format_mac_listesi(maclar, lig_adi), parse_mode="Markdown")

    elif islem == "puan":
        await query.edit_message_text("⏳ Puan durumu yükleniyor...")
        tablo = api.get_standings(lig_id)
        await query.edit_message_text(format_puan_durumu(tablo, lig_adi), parse_mode="Markdown")

    elif islem == "tahmin":
        await query.edit_message_text("⏳ Tahminler hesaplanıyor...")
        maclar = api.get_fixtures(lig_id=lig_id)
        if not maclar:
            await query.edit_message_text(f"📭 {lig_adi} için bugün maç bulunamadı.")
            return

        mesaj = f"🎯 *{lig_adi} TAHMİNLERİ*\n📅 {datetime.now().strftime('%d.%m.%Y')}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for mac in maclar[:5]:
            teams = mac.get("teams", {})
            fixture_id = mac.get("fixture", {}).get("id")
            ev_adi = teams.get("home", {}).get("name", "?")
            dep_adi = teams.get("away", {}).get("name", "?")
            ev_id = teams.get("home", {}).get("id")
            dep_id = teams.get("away", {}).get("id")

            prediction = api.get_predictions(fixture_id)
            ev_stats = tahmin_motoru.analiz_et(api.get_team_stats(ev_id, lig_id))
            dep_stats = tahmin_motoru.analiz_et(api.get_team_stats(dep_id, lig_id))
            tahmin_sonuc, guven = tahmin_motoru.tahmin_uret(ev_stats, dep_stats, prediction)

            cubuk = "█" * int(guven/10) + "░" * (10 - int(guven/10))
            mesaj += f"⚔️ *{ev_adi}* vs *{dep_adi}*\n"
            mesaj += f"   🏠 Form: `{ev_stats.get('form_str','?????')}`\n"
            mesaj += f"   ✈️ Form: `{dep_stats.get('form_str','?????')}`\n"
            mesaj += f"   💡 {tahmin_sonuc}\n"
            mesaj += f"   📈 [{cubuk}] %{guven}\n\n"

        mesaj += "⚠️ _Tahminler istatistiksel analize dayanır._"
        await query.edit_message_text(mesaj, parse_mode="Markdown")


async def gunluk_bildirim_gonder(context: ContextTypes.DEFAULT_TYPE):
    if not bildirim_listesi:
        return
    maclar = api.get_fixtures(lig_id=203) + api.get_fixtures(lig_id=39)
    mesaj = "🌅 *GÜNLÜK FUTBOL BÜLTENİ*\n\n" + format_mac_listesi(maclar[:10])
    for user_id in bildirim_listesi.copy():
        try:
            await context.bot.send_message(chat_id=user_id, text=mesaj, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Bildirim gönderilemedi {user_id}: {e}")
            bildirim_listesi.discard(user_id)


# ===================== MAIN =====================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bugun", bugun))
    app.add_handler(CommandHandler("canli", canli))
    app.add_handler(CommandHandler("puan", puan_durumu))
    app.add_handler(CommandHandler("tahmin", tahmin))
    app.add_handler(CommandHandler("bildirim", bildirim))
    app.add_handler(CommandHandler("hakkinda", hakkinda))
    app.add_handler(CallbackQueryHandler(button_handler))
    saat, dakika = map(int, BILDIRIM_SAATI.split(":"))
    app.job_queue.run_daily(gunluk_bildirim_gonder,
        time=datetime.now().replace(hour=saat, minute=dakika, second=0).time())
    logger.info("⚽ Futbol Bot başlatıldı!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
