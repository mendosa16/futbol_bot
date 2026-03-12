#!/usr/bin/env python3
"""
⚽ Futbol Analiz & Tahmin Telegram Botu
Sportmonks API v3 - Doğru Lig ID'leri
"""

import os
import logging
from datetime import datetime, timedelta
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
)

# ===================== AYARLAR =====================
TELEGRAM_TOKEN = "8610318322:AAFUcZ-pSbDIMiX_pK2t7mrWlJJQfdQLsrM"
SPORTMONKS_TOKEN = "DxHRy2fkqS7dWuNRckoxrmMdPQH0mRfvz7oMR5HGcNXQQrQrNjrgel1v8VIA"
BILDIRIM_SAATI = "08:00"
BASE_URL = "https://api.sportmonks.com/v3/football"

# ✅ Doğru Sportmonks Lig ID'leri
LIGLER = {
    "🇹🇷 Süper Lig":        600,
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier Lig":      8,
    "🇩🇪 Bundesliga":       82,
    "🇪🇸 La Liga":          564,
    "🇮🇹 Serie A":          384,
    "🇫🇷 Ligue 1":          301,
    "🇳🇱 Eredivisie":       72,
    "🇵🇹 Liga Portugal":    462,
    "🇧🇪 Pro League":       208,
    "🏆 Şampiyonlar Ligi":  2,
    "🌍 Avrupa Ligi":       5,
    "🇹🇷 Türkiye Kupası":   606,
}

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# ===================== API =====================
class SportmonksAPI:
    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()

    def _get(self, endpoint: str, params: dict = None) -> dict:
        if params is None:
            params = {}
        params["api_token"] = self.token
        try:
            resp = self.session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"API hatası [{endpoint}]: {e}")
            return {}

    def get_fixtures_by_date(self, tarih: str, lig_id: int = None) -> list:
        params = {
            "include": "participants;scores;state;league",
            "timezone": "Europe/Istanbul",
        }
        if lig_id:
            params["filters"] = f"fixtureLeagues:{lig_id}"
        return self._get(f"fixtures/date/{tarih}", params).get("data", [])

    def get_livescores(self) -> list:
        params = {"include": "participants;scores;state;league;events"}
        return self._get("livescores/inplay", params).get("data", [])

    def get_standings(self, season_id: int) -> list:
        params = {"include": "participant"}
        return self._get(f"standings/seasons/{season_id}", params).get("data", [])

    def get_league_season(self, league_id: int) -> int:
        """Ligin güncel sezon ID'sini döndürür."""
        params = {"include": "currentSeason"}
        data = self._get(f"leagues/{league_id}", params).get("data", {})
        # API bazen 'currentseason' (küçük harf) döndürür
        season = data.get("currentSeason") or data.get("currentseason") or {}
        return season.get("id", 0)

    def get_h2h(self, team1_id: int, team2_id: int) -> list:
        params = {"include": "participants;scores"}
        return self._get(f"fixtures/head-to-head/{team1_id}/{team2_id}", params).get("data", [])

    def get_topscorers(self, season_id: int) -> list:
        params = {"include": "player;participant"}
        return self._get(f"topscorers/seasons/{season_id}", params).get("data", [])


# ===================== YARDIMCI =====================
def get_team_name(fixture: dict, location: str) -> str:
    for p in fixture.get("participants", []):
        if p.get("meta", {}).get("location") == location:
            return p.get("name", "?")
    return "?"

def get_team_id(fixture: dict, location: str) -> int:
    for p in fixture.get("participants", []):
        if p.get("meta", {}).get("location") == location:
            return p.get("id", 0)
    return 0

def get_score(fixture: dict) -> tuple:
    h = a = None
    for score in fixture.get("scores", []):
        if score.get("description") == "CURRENT":
            goals = score.get("score", {})
            if goals.get("participant") == "home":
                h = goals.get("goals")
            elif goals.get("participant") == "away":
                a = goals.get("goals")
    return h, a

def get_state(fixture: dict) -> str:
    state = fixture.get("state", {})
    return state.get("short_name", "NS") if isinstance(state, dict) else "NS"

def format_time(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return (dt + timedelta(hours=3)).strftime("%H:%M")
    except:
        return "?"


# ===================== FORMAT =====================
def format_mac_listesi(maclar: list, lig_adi: str = "") -> str:
    if not maclar:
        return f"📭 {'Bugün' if not lig_adi else lig_adi} için maç bulunamadı."

    baslik = f"⚽ *{lig_adi} MAÇLARI*" if lig_adi else "⚽ *BUGÜNÜN MAÇLARI*"
    mesaj = f"{baslik} ({datetime.now().strftime('%d.%m.%Y')})\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for mac in maclar[:20]:
        ev = get_team_name(mac, "home")
        dep = get_team_name(mac, "away")
        durum = get_state(mac)
        saat = format_time(mac.get("starting_at", ""))
        h_gol, a_gol = get_score(mac)
        lig = mac.get("league", {}).get("name", "") if isinstance(mac.get("league"), dict) else ""

        if not lig_adi and lig:
            pass  # lig adı zaten başlıkta

        if durum == "FT":
            mesaj += f"✅ *{ev}* {h_gol}-{a_gol} *{dep}*\n"
        elif durum in ["1H", "2H", "HT", "ET"]:
            mesaj += f"🔴 *{ev}* {h_gol}-{a_gol} *{dep}* _{durum}_\n"
        else:
            mesaj += f"🕐 {saat} | *{ev}* vs *{dep}*\n"

    return mesaj


def format_standings(tablo: list, lig_adi: str) -> str:
    if not tablo:
        return "❌ Puan durumu alınamadı."

    mesaj = f"📊 *{lig_adi} PUAN DURUMU*\n━━━━━━━━━━━━━━━━━━━━━━\n"
    mesaj += "`#   Takım            O   G   B   M   P`\n"

    for satir in tablo[:18]:
        pos = satir.get("position", "?")
        takim = satir.get("participant", {}).get("name", "?")[:13].ljust(13)
        d = satir.get("details", {})
        o = str(d.get("games_played", 0)).rjust(2)
        g = str(d.get("won", 0)).rjust(2)
        b = str(d.get("draw", 0)).rjust(2)
        m = str(d.get("lost", 0)).rjust(2)
        p = str(satir.get("points", 0)).rjust(3)
        emoji = "🏆" if pos <= 4 else ("🔴" if pos >= len(tablo) - 2 else "  ")
        mesaj += f"`{str(pos).rjust(2)} {emoji}{takim} {o} {g} {b} {m} {p}`\n"

    return mesaj


# ===================== TAHMİN =====================
class TahminMotoru:

    @staticmethod
    def form_analiz(maclar: list, takim_id: int) -> dict:
        g = b = m = att = yedi = 0
        form_str = ""
        for mac in maclar[-6:]:
            h_gol, a_gol = get_score(mac)
            if h_gol is None:
                continue
            ev_mi = any(p.get("id") == takim_id and p.get("meta", {}).get("location") == "home"
                        for p in mac.get("participants", []))
            a, y = (h_gol, a_gol) if ev_mi else (a_gol, h_gol)
            att += a or 0
            yedi += y or 0
            if a > y: g += 1; form_str = "W" + form_str
            elif a == y: b += 1; form_str = "D" + form_str
            else: m += 1; form_str = "L" + form_str
        top = g + b + m
        return {
            "g": g, "b": b, "m": m, "att": att, "yedi": yedi,
            "form_puani": round((g * 3 + b) / max(top * 3, 1) * 100, 1),
            "form_str": form_str[:5] or "?????",
        }

    @staticmethod
    def h2h_analiz(maclar: list, ev_id: int) -> dict:
        eg = dg = b = 0
        for mac in maclar[-8:]:
            h, a = get_score(mac)
            if h is None: continue
            ev_mi = any(p.get("id") == ev_id and p.get("meta", {}).get("location") == "home"
                        for p in mac.get("participants", []))
            if ev_mi:
                if h > a: eg += 1
                elif h == a: b += 1
                else: dg += 1
            else:
                if a > h: eg += 1
                elif a == h: b += 1
                else: dg += 1
        return {"eg": eg, "dg": dg, "b": b, "toplam": eg + dg + b}

    @staticmethod
    def tahmin_uret(ev_form: dict, dep_form: dict, h2h: dict = None) -> tuple:
        ev_p = ev_form["form_puani"] + 10
        dep_p = dep_form["form_puani"]

        if h2h and h2h["toplam"] > 0:
            h2h_bonus = (h2h["eg"] - h2h["dg"]) / h2h["toplam"] * 15
            ev_p += h2h_bonus

        gol_bonus_ev = ev_form["att"] / max(ev_form["g"] + ev_form["b"] + ev_form["m"], 1) * 3
        gol_bonus_dep = dep_form["att"] / max(dep_form["g"] + dep_form["b"] + dep_form["m"], 1) * 3
        ev_p += gol_bonus_ev
        dep_p += gol_bonus_dep

        fark = ev_p - dep_p
        if fark > 18: return "🏠 Ev Sahibi Kazanır", min(83, 62 + int(fark / 2))
        elif fark > 8: return "🏠 Ev / Beraberlik", 57
        elif fark < -18: return "✈️ Deplasman Kazanır", min(81, 60 + int(abs(fark) / 2))
        elif fark < -8: return "✈️ Dep / Beraberlik", 55
        else: return "🤝 Beraberlik", 53


# ===================== BOT =====================
api = SportmonksAPI(SPORTMONKS_TOKEN)
tahmin_motoru = TahminMotoru()
bildirim_listesi: set = set()
_season_cache: dict = {}


def get_season_id(league_id: int) -> int:
    if league_id in _season_cache:
        return _season_cache[league_id]
    season_id = api.get_league_season(league_id)
    if season_id:
        _season_cache[league_id] = season_id
    return season_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ *FUTBOL ANALİZ & TAHMİN BOTU*\n\n"
        "📌 *Komutlar:*\n\n"
        "🗓 /bugun - Bugünün maçları\n"
        "🔴 /canli - Canlı maçlar\n"
        "📊 /puan - Puan durumu\n"
        "🎯 /tahmin - Maç tahminleri + H2H\n"
        "📈 /istatistik - Takım istatistikleri\n"
        "👑 /golkralligi - Gol krallığı\n"
        "🔔 /bildirim - Günlük bildirim\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Sportmonks API • 2500+ Lig",
        parse_mode="Markdown"
    )


async def bugun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"bugun|{i}")] for a, i in LIGLER.items()]
    keyboard.append([InlineKeyboardButton("🌍 Tüm Ligler", callback_data="bugun|0")])
    await update.message.reply_text(
        "🗓 *Hangi ligin maçlarını görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def canli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Canlı maçlar yükleniyor...")
    maclar = api.get_livescores()
    if not maclar:
        await update.message.reply_text("📭 Şu an canlı maç yok.")
        return
    mesaj = f"🔴 *CANLI MAÇLAR* ({len(maclar)} maç)\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for mac in maclar[:15]:
        ev = get_team_name(mac, "home")
        dep = get_team_name(mac, "away")
        h, a = get_score(mac)
        lig = mac.get("league", {}).get("name", "") if isinstance(mac.get("league"), dict) else ""
        mesaj += f"⚽ _{lig}_\n🔴 *{ev}* {h}-{a} *{dep}*\n\n"
    await update.message.reply_text(mesaj, parse_mode="Markdown")


async def puan_durumu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"puan|{i}")] for a, i in LIGLER.items()]
    await update.message.reply_text(
        "📊 *Hangi ligin puan durumunu görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def tahmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"tahmin|{i}")] for a, i in LIGLER.items()]
    await update.message.reply_text(
        "🎯 *Hangi lig için tahmin almak istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def istatistik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"istat|{i}")] for a, i in LIGLER.items()]
    await update.message.reply_text(
        "📈 *Hangi ligin istatistiklerini görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def golkralligi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"golkral|{i}")] for a, i in LIGLER.items()]
    await update.message.reply_text(
        "👑 *Hangi ligin gol krallığını görmek istiyorsun?*",
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
    islem, deger = query.data.split("|", 1)
    lig_id = int(deger)
    lig_adi = next((a for a, i in LIGLER.items() if i == lig_id), "Tüm Ligler")

    if islem == "bugun":
        await query.edit_message_text("⏳ Maçlar yükleniyor...")
        tarih = datetime.now().strftime("%Y-%m-%d")
        maclar = api.get_fixtures_by_date(tarih, lig_id if lig_id else None)
        await query.edit_message_text(format_mac_listesi(maclar, lig_adi), parse_mode="Markdown")

    elif islem == "puan":
        await query.edit_message_text("⏳ Puan durumu yükleniyor...")
        season_id = get_season_id(lig_id)
        if not season_id:
            await query.edit_message_text("❌ Sezon bilgisi alınamadı.")
            return
        tablo = api.get_standings(season_id)
        await query.edit_message_text(format_standings(tablo, lig_adi), parse_mode="Markdown")

    elif islem == "tahmin":
        await query.edit_message_text("⏳ Tahminler hazırlanıyor...")
        tarih = datetime.now().strftime("%Y-%m-%d")
        maclar = api.get_fixtures_by_date(tarih, lig_id)
        if not maclar:
            await query.edit_message_text(f"📭 {lig_adi} için bugün maç yok.")
            return

        mesaj = f"🎯 *{lig_adi} TAHMİNLERİ*\n📅 {datetime.now().strftime('%d.%m.%Y')}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for mac in maclar[:4]:
            ev_adi = get_team_name(mac, "home")
            dep_adi = get_team_name(mac, "away")
            ev_id = get_team_id(mac, "home")
            dep_id = get_team_id(mac, "away")
            saat = format_time(mac.get("starting_at", ""))

            h2h_maclar = api.get_h2h(ev_id, dep_id) if ev_id and dep_id else []
            h2h_data = tahmin_motoru.h2h_analiz(h2h_maclar, ev_id)
            ev_form = tahmin_motoru.form_analiz(h2h_maclar, ev_id)
            dep_form = tahmin_motoru.form_analiz(h2h_maclar, dep_id)
            tahmin_sonuc, guven = tahmin_motoru.tahmin_uret(ev_form, dep_form, h2h_data)
            cubuk = "█" * int(guven/10) + "░" * (10 - int(guven/10))

            mesaj += f"⚔️ *{ev_adi}* vs *{dep_adi}*\n"
            mesaj += f"   🕐 {saat}\n"
            mesaj += f"   🏠 Form: `{ev_form['form_str']}` ({ev_form['g']}G {ev_form['b']}B {ev_form['m']}M)\n"
            mesaj += f"   ✈️ Form: `{dep_form['form_str']}` ({dep_form['g']}G {dep_form['b']}B {dep_form['m']}M)\n"
            if h2h_data["toplam"] > 0:
                mesaj += f"   ⚔️ H2H son {h2h_data['toplam']} maç: {h2h_data['eg']}G {h2h_data['b']}B {h2h_data['dg']}M\n"
            mesaj += f"   💡 *{tahmin_sonuc}*\n"
            mesaj += f"   📈 [{cubuk}] %{guven}\n\n"

        mesaj += "⚠️ _Form ve H2H analizine dayanır._"
        await query.edit_message_text(mesaj, parse_mode="Markdown")

    elif islem == "istat":
        await query.edit_message_text("⏳ İstatistikler yükleniyor...")
        season_id = get_season_id(lig_id)
        if not season_id:
            await query.edit_message_text("❌ Sezon bilgisi alınamadı.")
            return
        tablo = api.get_standings(season_id)
        if not tablo:
            await query.edit_message_text("❌ Veri alınamadı.")
            return
        mesaj = f"📈 *{lig_adi} İSTATİSTİKLER*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for s in tablo[:10]:
            takim = s.get("participant", {}).get("name", "?")
            d = s.get("details", {})
            mesaj += f"🔵 *{takim}* — {s.get('points',0)} puan\n"
            mesaj += f"   {d.get('won',0)}G {d.get('draw',0)}B {d.get('lost',0)}M | ⚽{d.get('goals_scored','?')}/{d.get('goals_against','?')}\n\n"
        await query.edit_message_text(mesaj, parse_mode="Markdown")

    elif islem == "golkral":
        await query.edit_message_text("⏳ Gol krallığı yükleniyor...")
        season_id = get_season_id(lig_id)
        if not season_id:
            await query.edit_message_text("❌ Sezon bilgisi alınamadı.")
            return
        skorerler = api.get_topscorers(season_id)
        if not skorerler:
            await query.edit_message_text("❌ Gol krallığı verisi alınamadı.")
            return
        mesaj = f"👑 *{lig_adi} GOL KRALLIGI*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, s in enumerate(skorerler[:10], 1):
            oyuncu = s.get("player", {}).get("name", "?") if isinstance(s.get("player"), dict) else "?"
            takim = s.get("participant", {}).get("name", "?") if isinstance(s.get("participant"), dict) else "?"
            gol = s.get("total", "?")
            mesaj += f"{i}. *{oyuncu}* — {gol} ⚽\n   _{takim}_\n\n"
        await query.edit_message_text(mesaj, parse_mode="Markdown")


async def gunluk_bildirim_gonder(context: ContextTypes.DEFAULT_TYPE):
    if not bildirim_listesi:
        return
    tarih = datetime.now().strftime("%Y-%m-%d")
    maclar = api.get_fixtures_by_date(tarih, 600) + api.get_fixtures_by_date(tarih, 8)
    mesaj = f"🌅 *GÜNLÜK FUTBOL BÜLTENİ*\n{datetime.now().strftime('%d.%m.%Y')}\n\n"
    mesaj += format_mac_listesi(maclar[:12])
    for user_id in bildirim_listesi.copy():
        try:
            await context.bot.send_message(chat_id=user_id, text=mesaj, parse_mode="Markdown")
        except:
            bildirim_listesi.discard(user_id)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bugun", bugun))
    app.add_handler(CommandHandler("canli", canli))
    app.add_handler(CommandHandler("puan", puan_durumu))
    app.add_handler(CommandHandler("tahmin", tahmin))
    app.add_handler(CommandHandler("istatistik", istatistik))
    app.add_handler(CommandHandler("golkralligi", golkralligi))
    app.add_handler(CommandHandler("bildirim", bildirim))
    app.add_handler(CallbackQueryHandler(button_handler))
    saat, dakika = map(int, BILDIRIM_SAATI.split(":"))
    app.job_queue.run_daily(
        gunluk_bildirim_gonder,
        time=datetime.now().replace(hour=saat, minute=dakika, second=0).time()
    )
    logger.info("⚽ Futbol Bot v3 başlatıldı!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
