#!/usr/bin/env python3
"""
⚽ Futbol Analiz & Tahmin Telegram Botu
Sportmonks API v3 - 2500+ Lig
Özellikler:
  - Bugünün maçları (tüm ligler)
  - Canlı skorlar (gerçek zamanlı)
  - Puan durumu
  - Maç tahminleri (form + H2H + istatistik)
  - Takım & oyuncu istatistikleri
  - H2H (kafa kafaya geçmiş maçlar)
  - Günlük bildirim
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

# Popüler ligler (Sportmonks league ID'leri)
LIGLER = {
    "🇹🇷 Süper Lig":       271,
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier Lig":     8,
    "🇩🇪 Bundesliga":      82,
    "🇪🇸 La Liga":         564,
    "🇮🇹 Serie A":         384,
    "🇫🇷 Ligue 1":         301,
    "🏆 Şampiyonlar Ligi": 2,
    "🌍 Avrupa Ligi":      5,
    "🇳🇱 Eredivisie":      72,
    "🇵🇹 Primeira Liga":   462,
    "🇧🇪 Jupiler Pro":     208,
    "🇺🇸 MLS":             1296,
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ===================== API SINIFI =====================
class SportmonksAPI:
    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()

    def _get(self, endpoint: str, params: dict = None) -> dict:
        if params is None:
            params = {}
        params["api_token"] = self.token
        try:
            resp = self.session.get(
                f"{BASE_URL}/{endpoint}",
                params=params,
                timeout=15
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"API hatası [{endpoint}]: {e}")
            return {}

    def get_fixtures_by_date(self, tarih: str, lig_id: int = None) -> list:
        """Tarihe göre maçları çeker."""
        params = {
            "include": "participants;scores;state;league",
            "timezone": "Europe/Istanbul",
        }
        if lig_id:
            params["filters"] = f"fixtureLeagues:{lig_id}"

        data = self._get(f"fixtures/date/{tarih}", params)
        return data.get("data", [])

    def get_livescores(self) -> list:
        """Canlı maçları çeker."""
        params = {
            "include": "participants;scores;state;events;league",
        }
        data = self._get("livescores/inplay", params)
        return data.get("data", [])

    def get_standings(self, season_id: int) -> list:
        """Puan durumunu çeker."""
        params = {
            "include": "participant",
        }
        data = self._get(f"standings/seasons/{season_id}", params)
        return data.get("data", [])

    def get_league_seasons(self, league_id: int) -> dict:
        """Ligin güncel sezonunu çeker."""
        params = {"include": "currentSeason"}
        data = self._get(f"leagues/{league_id}", params)
        return data.get("data", {})

    def get_team_stats(self, team_id: int, season_id: int) -> dict:
        """Takım istatistiklerini çeker."""
        params = {
            "include": "statistics",
            "filters": f"statisticSeasons:{season_id}",
        }
        data = self._get(f"teams/{team_id}", params)
        return data.get("data", {})

    def get_h2h(self, team1_id: int, team2_id: int) -> list:
        """Kafa kafaya geçmiş maçları çeker."""
        params = {
            "include": "participants;scores",
        }
        data = self._get(f"fixtures/head-to-head/{team1_id}/{team2_id}", params)
        return data.get("data", [])

    def get_fixture_detail(self, fixture_id: int) -> dict:
        """Maç detaylarını çeker."""
        params = {
            "include": "participants;scores;events;statistics;lineups;predictions",
        }
        data = self._get(f"fixtures/{fixture_id}", params)
        return data.get("data", {})

    def get_topscorers(self, season_id: int) -> list:
        """Gol krallığını çeker."""
        params = {
            "include": "player;participant",
        }
        data = self._get(f"topscorers/seasons/{season_id}", params)
        return data.get("data", [])


# ===================== YARDIMCI FONKSİYONLAR =====================
def get_team_name(fixture: dict, location: str) -> str:
    """Maçtan takım adını çeker (home/away)."""
    for p in fixture.get("participants", []):
        meta = p.get("meta", {})
        if meta.get("location") == location:
            return p.get("name", "?")
    return "?"


def get_score(fixture: dict) -> tuple:
    """Maçtan skoru çeker."""
    home_score = away_score = None
    for score in fixture.get("scores", []):
        desc = score.get("description", "")
        if desc == "CURRENT":
            goals = score.get("score", {})
            if goals.get("participant") == "home":
                home_score = goals.get("goals")
            elif goals.get("participant") == "away":
                away_score = goals.get("goals")
    return home_score, away_score


def get_state(fixture: dict) -> str:
    """Maç durumunu çeker."""
    state = fixture.get("state", {})
    if isinstance(state, dict):
        return state.get("short_name", state.get("name", "NS"))
    return "NS"


def format_time(dt_str: str) -> str:
    """UTC zamanını TR saatine çevirir."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        dt_tr = dt + timedelta(hours=3)
        return dt_tr.strftime("%H:%M")
    except:
        return "?"


def format_mac_listesi(maclar: list, lig_adi: str = "") -> str:
    if not maclar:
        return f"📭 {'Bugün' if not lig_adi else lig_adi} için maç bulunamadı."

    baslik = f"⚽ *{lig_adi} MAÇLARI*" if lig_adi else "⚽ *BUGÜNÜN MAÇLARI*"
    mesaj = f"{baslik} ({datetime.now().strftime('%d.%m.%Y')})\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

    # Lige göre grupla
    grouped = {}
    for mac in maclar:
        lig = mac.get("league", {})
        lig_name = lig.get("name", "Diğer") if isinstance(lig, dict) else "Diğer"
        grouped.setdefault(lig_name, []).append(mac)

    for lig_name, lig_maclar in list(grouped.items())[:8]:
        if not lig_adi:
            mesaj += f"🏆 _{lig_name}_\n"
        for mac in lig_maclar[:6]:
            ev = get_team_name(mac, "home")
            dep = get_team_name(mac, "away")
            durum = get_state(mac)
            saat = format_time(mac.get("starting_at", ""))
            h_gol, a_gol = get_score(mac)

            if durum == "FT":
                mesaj += f"✅ *{ev}* {h_gol}-{a_gol} *{dep}*\n"
            elif durum in ["1H", "2H", "HT", "ET", "LIVE"]:
                elapsed = mac.get("periods", [{}])
                mesaj += f"🔴 *{ev}* {h_gol}-{a_gol} *{dep}*\n"
            else:
                mesaj += f"🕐 {saat} | *{ev}* vs *{dep}*\n"
        mesaj += "\n"

    return mesaj.strip()


def format_standings(tablo: list, lig_adi: str) -> str:
    if not tablo:
        return "❌ Puan durumu alınamadı."

    mesaj = f"📊 *{lig_adi} PUAN DURUMU*\n━━━━━━━━━━━━━━━━━━━━━━\n"
    mesaj += "`#   Takım            O   G   B   M   P`\n"

    for satir in tablo[:18]:
        pos = satir.get("position", "?")
        takim = satir.get("participant", {}).get("name", "?")[:13].ljust(13)
        detay = satir.get("details", {})
        o = str(detay.get("games_played", 0)).rjust(2)
        g = str(detay.get("won", 0)).rjust(2)
        b = str(detay.get("draw", 0)).rjust(2)
        m = str(detay.get("lost", 0)).rjust(2)
        p = str(satir.get("points", 0)).rjust(3)

        if pos <= 4:
            emoji = "🏆"
        elif pos >= len(tablo) - 2:
            emoji = "🔴"
        else:
            emoji = "  "

        mesaj += f"`{str(pos).rjust(2)} {emoji}{takim} {o} {g} {b} {m} {p}`\n"

    return mesaj


# ===================== TAHMİN MOTORU =====================
class TahminMotoru:

    @staticmethod
    def form_analiz(mac_listesi: list, takim_id: int) -> dict:
        """Son 5 maçtan form analizi."""
        galibiyet = beraberlik = maglubiyet = 0
        gol_atti = gol_yedi = 0
        form_str = ""

        for mac in mac_listesi[-5:]:
            h_gol, a_gol = get_score(mac)
            if h_gol is None:
                continue

            ev_mi = any(
                p.get("id") == takim_id and p.get("meta", {}).get("location") == "home"
                for p in mac.get("participants", [])
            )

            if ev_mi:
                att, yedi = h_gol, a_gol
            else:
                att, yedi = a_gol, h_gol

            gol_atti += att or 0
            gol_yedi += yedi or 0

            if att > yedi:
                galibiyet += 1
                form_str = "W" + form_str
            elif att == yedi:
                beraberlik += 1
                form_str = "D" + form_str
            else:
                maglubiyet += 1
                form_str = "L" + form_str

        toplam = galibiyet + beraberlik + maglubiyet
        form_puani = (galibiyet * 3 + beraberlik) / max(toplam * 3, 1) * 100

        return {
            "g": galibiyet, "b": beraberlik, "m": maglubiyet,
            "gol_atti": gol_atti, "gol_yedi": gol_yedi,
            "form_puani": round(form_puani, 1),
            "form_str": form_str[:5] or "?????",
        }

    @staticmethod
    def h2h_analiz(h2h_maclar: list, ev_id: int) -> dict:
        """H2H analizini yapar."""
        ev_galibiyet = dep_galibiyet = beraberlik = 0
        for mac in h2h_maclar[-10:]:
            h_gol, a_gol = get_score(mac)
            if h_gol is None:
                continue
            ev_mi = any(
                p.get("id") == ev_id and p.get("meta", {}).get("location") == "home"
                for p in mac.get("participants", [])
            )
            if ev_mi:
                if h_gol > a_gol: ev_galibiyet += 1
                elif h_gol == a_gol: beraberlik += 1
                else: dep_galibiyet += 1
            else:
                if a_gol > h_gol: ev_galibiyet += 1
                elif a_gol == h_gol: beraberlik += 1
                else: dep_galibiyet += 1
        return {"ev_g": ev_galibiyet, "dep_g": dep_galibiyet, "b": beraberlik}

    @staticmethod
    def tahmin_uret(ev_form: dict, dep_form: dict, h2h: dict = None) -> tuple:
        """Kapsamlı tahmin üretir."""
        ev_puan = ev_form["form_puani"] + 10  # ev avantajı
        dep_puan = dep_form["form_puani"]

        # H2H bonusu
        if h2h:
            toplam_h2h = h2h["ev_g"] + h2h["dep_g"] + h2h["b"]
            if toplam_h2h > 0:
                h2h_bonus = (h2h["ev_g"] - h2h["dep_g"]) / toplam_h2h * 15
                ev_puan += h2h_bonus

        # Gol ortalaması bonusu
        ev_gol_ort = ev_form["gol_atti"] / max(ev_form["g"] + ev_form["b"] + ev_form["m"], 1)
        dep_gol_ort = dep_form["gol_atti"] / max(dep_form["g"] + dep_form["b"] + dep_form["m"], 1)
        ev_puan += ev_gol_ort * 3
        dep_puan += dep_gol_ort * 3

        fark = ev_puan - dep_puan

        if fark > 18:
            return "🏠 Ev Sahibi Kazanır", min(82, 62 + int(fark / 2))
        elif fark > 8:
            return "🏠 Ev Sahibi / Beraberlik", 58
        elif fark < -18:
            return "✈️ Deplasman Kazanır", min(80, 60 + int(abs(fark) / 2))
        elif fark < -8:
            return "✈️ Deplasman / Beraberlik", 56
        else:
            return "🤝 Beraberlik", 54


# ===================== BOT =====================
api = SportmonksAPI(SPORTMONKS_TOKEN)
tahmin_motoru = TahminMotoru()
bildirim_listesi: set = set()

# Sezon ID cache
_season_cache: dict = {}


def get_season_id(league_id: int) -> int:
    """Ligin güncel sezon ID'sini döndürür (cache'li)."""
    if league_id in _season_cache:
        return _season_cache[league_id]
    lig_data = api.get_league_seasons(league_id)
    season = lig_data.get("currentSeason", {})
    season_id = season.get("id", 0)
    if season_id:
        _season_cache[league_id] = season_id
    return season_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ *FUTBOL ANALİZ & TAHMİN BOTUNA HOŞGELDİN!*\n\n"
        "📌 *Komutlar:*\n\n"
        "🗓 /bugun - Bugünün maçları\n"
        "🔴 /canli - Canlı maçlar\n"
        "📊 /puan - Puan durumu\n"
        "🎯 /tahmin - Maç tahminleri\n"
        "📈 /istatistik - Takım istatistikleri\n"
        "⚔️ /h2h - Kafa kafaya analiz\n"
        "👑 /golkralligi - Gol krallığı\n"
        "🔔 /bildirim - Günlük bildirim\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Sportmonks API • 2500+ lig",
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
        h_gol, a_gol = get_score(mac)
        lig = mac.get("league", {}).get("name", "") if isinstance(mac.get("league"), dict) else ""
        durum = get_state(mac)

        # Gol olaylarını bul
        son_olay = ""
        for event in mac.get("events", [])[-3:]:
            tip = event.get("type", {})
            if isinstance(tip, dict) and "goal" in tip.get("name", "").lower():
                oyuncu = event.get("player_name", "")
                dakika = event.get("minute", "")
                son_olay = f"⚽ {dakika}' {oyuncu}"

        mesaj += f"🔴 _{lig}_\n"
        mesaj += f"*{ev}* {h_gol} - {a_gol} *{dep}*\n"
        if son_olay:
            mesaj += f"   {son_olay}\n"
        mesaj += "\n"

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


async def h2h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚔️ *H2H Analizi*\n\n"
        "Kullanım: `/h2h TAKIM_ID1 TAKIM_ID2`\n\n"
        "Önce /bugun komutuyla bir maç seç, "
        "maça tıklayınca H2H analizi otomatik gelecek!",
        parse_mode="Markdown"
    )


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
        await query.edit_message_text(
            format_mac_listesi(maclar, lig_adi),
            parse_mode="Markdown"
        )

    elif islem == "puan":
        await query.edit_message_text("⏳ Puan durumu yükleniyor...")
        season_id = get_season_id(lig_id)
        if not season_id:
            await query.edit_message_text("❌ Sezon bilgisi alınamadı.")
            return
        tablo = api.get_standings(season_id)
        await query.edit_message_text(
            format_standings(tablo, lig_adi),
            parse_mode="Markdown"
        )

    elif islem == "tahmin":
        await query.edit_message_text("⏳ Maçlar ve tahminler yükleniyor...")
        tarih = datetime.now().strftime("%Y-%m-%d")
        maclar = api.get_fixtures_by_date(tarih, lig_id)

        if not maclar:
            await query.edit_message_text(f"📭 {lig_adi} için bugün maç yok.")
            return

        mesaj = f"🎯 *{lig_adi} TAHMİNLERİ*\n📅 {datetime.now().strftime('%d.%m.%Y')}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

        for mac in maclar[:4]:
            ev_adi = get_team_name(mac, "home")
            dep_adi = get_team_name(mac, "away")
            saat = format_time(mac.get("starting_at", ""))
            fixture_id = mac.get("id")

            # Takım ID'lerini al
            ev_id = dep_id = None
            for p in mac.get("participants", []):
                if p.get("meta", {}).get("location") == "home":
                    ev_id = p.get("id")
                else:
                    dep_id = p.get("id")

            # H2H çek
            h2h_data = {}
            if ev_id and dep_id:
                h2h_maclar = api.get_h2h(ev_id, dep_id)
                h2h_data = tahmin_motoru.h2h_analiz(h2h_maclar, ev_id)

                # Form analizi (son maçlardan)
                ev_son_maclar = [m for m in h2h_maclar if any(
                    p.get("id") == ev_id for p in m.get("participants", [])
                )]
                dep_son_maclar = [m for m in h2h_maclar if any(
                    p.get("id") == dep_id for p in m.get("participants", [])
                )]
                ev_form = tahmin_motoru.form_analiz(ev_son_maclar, ev_id)
                dep_form = tahmin_motoru.form_analiz(dep_son_maclar, dep_id)
            else:
                ev_form = dep_form = {"form_puani": 50, "form_str": "?????", "g": 0, "b": 0, "m": 0, "gol_atti": 0, "gol_yedi": 0}

            tahmin_sonuc, guven = tahmin_motoru.tahmin_uret(ev_form, dep_form, h2h_data)
            cubuk = "█" * int(guven/10) + "░" * (10 - int(guven/10))

            mesaj += f"⚔️ *{ev_adi}* vs *{dep_adi}*\n"
            mesaj += f"   🕐 {saat}\n"
            mesaj += f"   🏠 Form: `{ev_form['form_str']}` ({ev_form['g']}G {ev_form['b']}B {ev_form['m']}M)\n"
            mesaj += f"   ✈️ Form: `{dep_form['form_str']}` ({dep_form['g']}G {dep_form['b']}B {dep_form['m']}M)\n"
            if h2h_data:
                mesaj += f"   ⚔️ H2H: {h2h_data['ev_g']}G {h2h_data['b']}B {h2h_data['dep_g']}M\n"
            mesaj += f"   💡 *{tahmin_sonuc}*\n"
            mesaj += f"   📈 [{cubuk}] %{guven}\n\n"

        mesaj += "⚠️ _İstatistik ve H2H analizine dayanır._"
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

        mesaj = f"📈 *{lig_adi} TAKIM İSTATİSTİKLERİ*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for s in tablo[:8]:
            takim = s.get("participant", {}).get("name", "?")
            d = s.get("details", {})
            gf = d.get("goals_scored", "?")
            ga = d.get("goals_against", "?")
            g = d.get("won", 0)
            b = d.get("draw", 0)
            m = d.get("lost", 0)
            p = s.get("points", 0)
            mesaj += f"🔵 *{takim}* — {p} puan\n"
            mesaj += f"   {g}G {b}B {m}M | ⚽ {gf} Gol / {ga} Yenilen\n\n"

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
            mesaj += f"{i}. *{oyuncu}* — {gol} gol\n   _{takim}_\n\n"

        await query.edit_message_text(mesaj, parse_mode="Markdown")


async def gunluk_bildirim_gonder(context: ContextTypes.DEFAULT_TYPE):
    if not bildirim_listesi:
        return
    tarih = datetime.now().strftime("%Y-%m-%d")
    # Süper Lig + Premier Lig
    maclar = api.get_fixtures_by_date(tarih, 271) + api.get_fixtures_by_date(tarih, 8)
    mesaj = f"🌅 *GÜNLÜK FUTBOL BÜLTENİ*\n{datetime.now().strftime('%d.%m.%Y')}\n\n"
    mesaj += format_mac_listesi(maclar[:10])

    for user_id in bildirim_listesi.copy():
        try:
            await context.bot.send_message(chat_id=user_id, text=mesaj, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Bildirim hatası {user_id}: {e}")
            bildirim_listesi.discard(user_id)


# ===================== MAIN =====================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bugun", bugun))
    app.add_handler(CommandHandler("canli", canli))
    app.add_handler(CommandHandler("puan", puan_durumu))
    app.add_handler(CommandHandler("tahmin", tahmin))
    app.add_handler(CommandHandler("istatistik", istatistik))
    app.add_handler(CommandHandler("golkralligi", golkralligi))
    app.add_handler(CommandHandler("h2h", h2h))
    app.add_handler(CommandHandler("bildirim", bildirim))
    app.add_handler(CallbackQueryHandler(button_handler))

    saat, dakika = map(int, BILDIRIM_SAATI.split(":"))
    app.job_queue.run_daily(
        gunluk_bildirim_gonder,
        time=datetime.now().replace(hour=saat, minute=dakika, second=0).time()
    )
    logger.info("⚽ Futbol Bot v3 (Sportmonks) başlatıldı!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
