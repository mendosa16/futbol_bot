#!/usr/bin/env python3
import os
import logging
from datetime import datetime, timedelta
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TELEGRAM_TOKEN = "8610318322:AAFUcZ-pSbDIMiX_pK2t7mrWlJJQfdQLsrM"
SPORTMONKS_TOKEN = "DxHRy2fkqS7dWuNRckoxrmMdPQH0mRfvz7oMR5HGcNXQQrQrNjrgel1v8VIA"
BILDIRIM_SAATI = "08:00"
BASE_URL = "https://api.sportmonks.com/v3/football"

LIGLER = {
    "Sper Lig":        600,
    "Premier Lig":      8,
    "Bundesliga":       82,
    "La Liga":          564,
    "Serie A":          384,
    "Ligue 1":          301,
    "Eredivisie":       72,
    "Liga Portugal":    462,
    "Pro League":       208,
    "Sampiyonlar Ligi": 2,
    "Avrupa Ligi":      5,
    "Turkiye Kupasi":   606,
}

LIG_EMOJI = {
    600: "TR", 8: "EN", 82: "DE", 564: "ES", 384: "IT",
    301: "FR", 72: "NL", 462: "PT", 208: "BE", 2: "UCL", 5: "UEL", 606: "CUP"
}

TUMU_LIG_IDS = list(LIGLER.values())
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


class SportmonksAPI:
    def __init__(self, token):
        self.token = token
        self.session = requests.Session()

    def _get(self, endpoint, params=None):
        if params is None:
            params = {}
        params["api_token"] = self.token
        try:
            r = self.session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"API [{endpoint}]: {e}")
            return {}

    def get_fixtures_by_date(self, tarih, lig_id=None):
        params = {
            "include": "participants;scores;state;league",
            "timezone": "Europe/Istanbul",
        }
        if lig_id:
            params["filters"] = f"fixtureLeagues:{lig_id}"
        return self._get(f"fixtures/date/{tarih}", params).get("data", [])

    def get_fixtures_multi_league(self, tarih, lig_ids):
        lig_str = ",".join(str(i) for i in lig_ids)
        params = {
            "include": "participants;scores;state;league",
            "timezone": "Europe/Istanbul",
            "filters": f"fixtureLeagues:{lig_str}",
        }
        return self._get(f"fixtures/date/{tarih}", params).get("data", [])

    def get_livescores(self):
        params = {"include": "participants;scores;state;league"}
        return self._get("livescores/inplay", params).get("data", [])

    def get_standings(self, season_id):
        params = {"include": "participant;details"}
        return self._get(f"standings/seasons/{season_id}", params).get("data", [])

    def get_league_season(self, league_id):
        params = {"include": "currentSeason"}
        data = self._get(f"leagues/{league_id}", params).get("data", {})
        season = data.get("currentSeason") or data.get("currentseason") or {}
        return season.get("id", 0)

    def get_h2h(self, team1_id, team2_id):
        params = {"include": "participants;scores"}
        return self._get(f"fixtures/head-to-head/{team1_id}/{team2_id}", params).get("data", [])

    def get_topscorers(self, season_id):
        params = {"include": "player;participant"}
        return self._get(f"topscorers/seasons/{season_id}", params).get("data", [])


def get_team_name(fixture, location):
    for p in fixture.get("participants", []):
        if p.get("meta", {}).get("location") == location:
            return p.get("name", "?")
    return "?"

def get_team_id(fixture, location):
    for p in fixture.get("participants", []):
        if p.get("meta", {}).get("location") == location:
            return p.get("id", 0)
    return 0

def get_score(fixture):
    h = a = None
    for s in fixture.get("scores", []):
        if s.get("description") == "CURRENT":
            sc = s.get("score", {})
            if sc.get("participant") == "home":
                h = sc.get("goals", 0)
            elif sc.get("participant") == "away":
                a = sc.get("goals", 0)
    return h, a

def get_state(fixture):
    state = fixture.get("state", {})
    if isinstance(state, dict):
        return state.get("short_name", "NS")
    return "NS"

def format_time(dt_str):
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return (dt + timedelta(hours=3)).strftime("%H:%M")
    except Exception:
        return "?"

def parse_details(details):
    result = {}
    if isinstance(details, list):
        mapping = {129: "o", 130: "g", 131: "b", 132: "m", 133: "gf", 134: "ga", 179: "avg"}
        for item in details:
            tid = item.get("type_id")
            if tid in mapping:
                result[mapping[tid]] = item.get("value", 0)
    return result


def format_mac_listesi(maclar, lig_adi=""):
    if not maclar:
        label = lig_adi if lig_adi else "Bugun"
        return f"Bugün {label} için maç bulunamadı."

    baslik = f"MACLAR: {lig_adi}" if lig_adi else "BUGÜNÜN MAÇLARI"
    tarih_str = datetime.now().strftime("%d.%m.%Y")
    mesaj = f"*{baslik}* ({tarih_str})\n"
    mesaj += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

    grouped = {}
    for mac in maclar:
        lig_obj = mac.get("league", {})
        lig_name = lig_obj.get("name", "Diger") if isinstance(lig_obj, dict) else "Diger"
        grouped.setdefault(lig_name, []).append(mac)

    for lig_name, lig_maclar in grouped.items():
        if not lig_adi:
            mesaj += f"*{lig_name}*\n"
        for mac in lig_maclar:
            ev = get_team_name(mac, "home")
            dep = get_team_name(mac, "away")
            durum = get_state(mac)
            saat = format_time(mac.get("starting_at", ""))
            h, a = get_score(mac)
            if durum == "FT":
                mesaj += f"   *{ev}* {h}-{a} *{dep}*\n"
            elif durum in ["1H", "2H", "HT", "ET", "LIVE"]:
                mesaj += f"   CANLI *{ev}* {h}-{a} *{dep}* ({durum})\n"
            else:
                mesaj += f"   {saat} | {ev} vs {dep}\n"
        mesaj += "\n"
    return mesaj.strip()


def format_standings(tablo, lig_adi):
    if not tablo:
        return "Puan durumu alinamadi."
    mesaj = f"*{lig_adi} PUAN DURUMU*\n"
    mesaj += "━━━━━━━━━━━━━━━━━━━━━━\n"
    mesaj += "`#   Takim            O  G  B  M   P  Av`\n"
    for satir in tablo[:18]:
        pos = satir.get("position", 0)
        takim = satir.get("participant", {}).get("name", "?")[:13].ljust(13)
        d = parse_details(satir.get("details", []))
        o = str(d.get("o", 0)).rjust(2)
        g = str(d.get("g", 0)).rjust(2)
        b = str(d.get("b", 0)).rjust(2)
        m = str(d.get("m", 0)).rjust(2)
        p = str(satir.get("points", 0)).rjust(3)
        avg = d.get("avg", 0)
        avg_str = (f"+{avg}" if avg > 0 else str(avg)).rjust(3)
        emoji = "TP" if pos <= 4 else ("D" if pos >= len(tablo) - 2 else " ")
        mesaj += f"`{str(pos).rjust(2)} {emoji} {takim} {o} {g} {b} {m} {p} {avg_str}`\n"
    return mesaj


class TahminMotoru:
    @staticmethod
    def form_analiz(maclar, takim_id):
        g = b = m = att = yedi = 0
        form_str = ""
        for mac in maclar[-6:]:
            h, a = get_score(mac)
            if h is None:
                continue
            ev_mi = any(
                p.get("id") == takim_id and p.get("meta", {}).get("location") == "home"
                for p in mac.get("participants", [])
            )
            at_, ye_ = (h, a) if ev_mi else (a, h)
            att += at_ or 0
            yedi += ye_ or 0
            if at_ > ye_:
                g += 1
                form_str = "W" + form_str
            elif at_ == ye_:
                b += 1
                form_str = "D" + form_str
            else:
                m += 1
                form_str = "L" + form_str
        top = g + b + m
        return {
            "g": g, "b": b, "m": m, "att": att, "yedi": yedi,
            "form_puani": round((g * 3 + b) / max(top * 3, 1) * 100, 1),
            "form_str": form_str[:5] or "?????",
        }

    @staticmethod
    def h2h_analiz(maclar, ev_id):
        eg = dg = b = 0
        for mac in maclar[-8:]:
            h, a = get_score(mac)
            if h is None:
                continue
            ev_mi = any(
                p.get("id") == ev_id and p.get("meta", {}).get("location") == "home"
                for p in mac.get("participants", [])
            )
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
    def tahmin_uret(ev_form, dep_form, h2h=None):
        ev_p = ev_form["form_puani"] + 10
        dep_p = dep_form["form_puani"]
        if h2h and h2h["toplam"] > 0:
            ev_p += (h2h["eg"] - h2h["dg"]) / h2h["toplam"] * 15
        top_ev = max(ev_form["g"] + ev_form["b"] + ev_form["m"], 1)
        top_dep = max(dep_form["g"] + dep_form["b"] + dep_form["m"], 1)
        ev_p += ev_form["att"] / top_ev * 3
        dep_p += dep_form["att"] / top_dep * 3
        fark = ev_p - dep_p
        if fark > 18: return "Ev Sahibi Kazanir", min(83, 62 + int(fark / 2))
        elif fark > 8: return "Ev / Beraberlik", 57
        elif fark < -18: return "Deplasman Kazanir", min(81, 60 + int(abs(fark) / 2))
        elif fark < -8: return "Dep / Beraberlik", 55
        else: return "Beraberlik", 53


api = SportmonksAPI(SPORTMONKS_TOKEN)
tahmin_motoru = TahminMotoru()
bildirim_listesi = set()
_season_cache = {}


def get_season_id(league_id):
    if league_id not in _season_cache:
        sid = api.get_league_season(league_id)
        if sid:
            _season_cache[league_id] = sid
    return _season_cache.get(league_id, 0)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*FUTBOL ANALIZ BOTUNA HOSGELDIN!*\n\n"
        "/bugun - Bugünün maçları\n"
        "/canli - Canlı maçlar\n"
        "/puan - Puan durumu\n"
        "/tahmin - Maç tahminleri + H2H\n"
        "/istatistik - Takım istatistikleri\n"
        "/golkralligi - Gol krallığı\n"
        "/bildirim - Günlük bildirim\n\n"
        "Sportmonks API - 2500+ Lig"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def bugun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"bugun|{i}")] for a, i in LIGLER.items()]
    keyboard.append([InlineKeyboardButton("Tüm Seçili Ligler", callback_data="bugun|0")])
    await update.message.reply_text(
        "Hangi ligin maçlarını görmek istiyorsun?",
        reply_markup=InlineKeyboardMarkup(keyboard))


async def canli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Canlı maçlar yükleniyor...")
    maclar = api.get_livescores()
    secili = [m for m in maclar if m.get("league", {}).get("id") in TUMU_LIG_IDS]
    goster = secili if secili else maclar[:15]
    if not goster:
        await update.message.reply_text("Şu an canlı maç yok.")
        return
    mesaj = f"*CANLI MAÇLAR* ({len(goster)} maç)\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for mac in goster[:15]:
        ev = get_team_name(mac, "home")
        dep = get_team_name(mac, "away")
        h, a = get_score(mac)
        lig_obj = mac.get("league", {})
        lig = lig_obj.get("name", "") if isinstance(lig_obj, dict) else ""
        durum = get_state(mac)
        mesaj += f"_{lig}_\n*{ev}* {h}-{a} *{dep}* ({durum})\n\n"
    await update.message.reply_text(mesaj, parse_mode="Markdown")


async def puan_durumu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"puan|{i}")] for a, i in LIGLER.items()]
    await update.message.reply_text("Hangi ligin puan durumunu görmek istiyorsun?",
                                    reply_markup=InlineKeyboardMarkup(keyboard))


async def tahmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"tahmin|{i}")] for a, i in LIGLER.items()]
    await update.message.reply_text("Hangi lig için tahmin almak istiyorsun?",
                                    reply_markup=InlineKeyboardMarkup(keyboard))


async def istatistik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"istat|{i}")] for a, i in LIGLER.items()]
    await update.message.reply_text("Hangi ligin istatistiklerini görmek istiyorsun?",
                                    reply_markup=InlineKeyboardMarkup(keyboard))


async def golkralligi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(a, callback_data=f"golkral|{i}")] for a, i in LIGLER.items()]
    await update.message.reply_text("Hangi ligin gol krallığını görmek istiyorsun?",
                                    reply_markup=InlineKeyboardMarkup(keyboard))


async def bildirim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in bildirim_listesi:
        bildirim_listesi.remove(user_id)
        await update.message.reply_text("Bildirimler kapatıldı.")
    else:
        bildirim_listesi.add(user_id)
        await update.message.reply_text(f"Bildirimler açıldı! Her gün {BILDIRIM_SAATI}'de özet gelecek.")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    islem, deger = query.data.split("|", 1)
    lig_id = int(deger)
    lig_adi = next((a for a, i in LIGLER.items() if i == lig_id), "Tum Ligler")
    tarih = datetime.now().strftime("%Y-%m-%d")

    if islem == "bugun":
        await query.edit_message_text("Maçlar yükleniyor...")
        if lig_id == 0:
            maclar = api.get_fixtures_multi_league(tarih, TUMU_LIG_IDS)
        else:
            maclar = api.get_fixtures_by_date(tarih, lig_id)
        await query.edit_message_text(format_mac_listesi(maclar, lig_adi), parse_mode="Markdown")

    elif islem == "puan":
        await query.edit_message_text("Puan durumu yükleniyor...")
        season_id = get_season_id(lig_id)
        if not season_id:
            await query.edit_message_text("Sezon bilgisi alinamadi.")
            return
        tablo = api.get_standings(season_id)
        await query.edit_message_text(format_standings(tablo, lig_adi), parse_mode="Markdown")

    elif islem == "tahmin":
        await query.edit_message_text("Tahminler hazırlanıyor...")
        maclar = api.get_fixtures_by_date(tarih, lig_id)
        if not maclar:
            await query.edit_message_text(f"{lig_adi} için bugün maç yok.")
            return
        tarih_str = datetime.now().strftime("%d.%m.%Y")
        mesaj = f"*{lig_adi} TAHMINLERI* - {tarih_str}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
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
            sonuc, guven = tahmin_motoru.tahmin_uret(ev_form, dep_form, h2h_data)
            cubuk = "X" * int(guven / 10) + "." * (10 - int(guven / 10))
            mesaj += f"*{ev_adi}* vs *{dep_adi}*\n"
            mesaj += f"   Saat: {saat}\n"
            mesaj += f"   Ev Form: {ev_form['form_str']} ({ev_form['g']}G {ev_form['b']}B {ev_form['m']}M)\n"
            mesaj += f"   Dep Form: {dep_form['form_str']} ({dep_form['g']}G {dep_form['b']}B {dep_form['m']}M)\n"
            if h2h_data["toplam"] > 0:
                mesaj += f"   H2H: {h2h_data['eg']}G {h2h_data['b']}B {h2h_data['dg']}M\n"
            mesaj += f"   *{sonuc}* [{cubuk}] %{guven}\n\n"
        mesaj += "_Istatistik ve H2H analizine dayanir._"
        await query.edit_message_text(mesaj, parse_mode="Markdown")

    elif islem == "istat":
        await query.edit_message_text("İstatistikler yükleniyor...")
        season_id = get_season_id(lig_id)
        if not season_id:
            await query.edit_message_text("Sezon bilgisi alinamadi.")
            return
        tablo = api.get_standings(season_id)
        if not tablo:
            await query.edit_message_text("Veri alinamadi.")
            return
        mesaj = f"*{lig_adi} ISTATISTIKLER*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for s in tablo[:12]:
            takim = s.get("participant", {}).get("name", "?")
            pos = s.get("position", "?")
            p = s.get("points", 0)
            d = parse_details(s.get("details", []))
            o = d.get("o", 0)
            g = d.get("g", 0)
            b = d.get("b", 0)
            m = d.get("m", 0)
            gf = d.get("gf", "?")
            ga = d.get("ga", "?")
            avg = d.get("avg", 0)
            avg_str = f"+{avg}" if avg > 0 else str(avg)
            mesaj += f"*{pos}. {takim}* - {p} puan\n"
            mesaj += f"   {o}mac: {g}G {b}B {m}M | {gf}/{ga} gol | Av:{avg_str}\n\n"
        await query.edit_message_text(mesaj, parse_mode="Markdown")

    elif islem == "golkral":
        await query.edit_message_text("Gol krallığı yükleniyor...")
        season_id = get_season_id(lig_id)
        if not season_id:
            await query.edit_message_text("Sezon bilgisi alinamadi.")
            return
        skorerler = api.get_topscorers(season_id)
        if not skorerler:
            await query.edit_message_text("Veri alinamadi.")
            return
        mesaj = f"*{lig_adi} GOL KRALLIGI*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, s in enumerate(skorerler[:10], 1):
            oyuncu = s.get("player", {}).get("name", "?") if isinstance(s.get("player"), dict) else "?"
            takim = s.get("participant", {}).get("name", "?") if isinstance(s.get("participant"), dict) else "?"
            gol = s.get("total", "?")
            mesaj += f"{i}. *{oyuncu}* - {gol} gol\n   _{takim}_\n\n"
        await query.edit_message_text(mesaj, parse_mode="Markdown")


async def gunluk_bildirim_gonder(context: ContextTypes.DEFAULT_TYPE):
    if not bildirim_listesi:
        return
    tarih = datetime.now().strftime("%Y-%m-%d")
    maclar = api.get_fixtures_multi_league(tarih, TUMU_LIG_IDS)
    mesaj = "GUNLUK FUTBOL BULTENI\n" + format_mac_listesi(maclar)
    for user_id in bildirim_listesi.copy():
        try:
            await context.bot.send_message(chat_id=user_id, text=mesaj, parse_mode="Markdown")
        except Exception:
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
    logger.info("Futbol Bot v4 basladi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
