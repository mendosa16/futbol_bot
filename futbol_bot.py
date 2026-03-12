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
    "🇹🇷 Süper Lig":        600,
    "🇹🇷 Türkiye Kupası":   606,
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier Lig":      8,
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Championship":      9,
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 FA Cup":            24,
    "🇩🇪 Bundesliga":       82,
    "🇩🇪 2. Bundesliga":    85,
    "🇪🇸 La Liga":          564,
    "🇪🇸 La Liga 2":        567,
    "🇪🇸 Copa Del Rey":     570,
    "🇮🇹 Serie A":          384,
    "🇮🇹 Serie B":          387,
    "🇮🇹 Coppa Italia":     390,
    "🇫🇷 Ligue 1":          301,
    "🇳🇱 Eredivisie":       72,
    "🇵🇹 Liga Portugal":    462,
    "🇧🇪 Pro League":       208,
    "🏴󠁧󠁢󠁳󠁣󠁴󠁿 Premiership":      501,
    "🇦🇹 Avusturya BL":     181,
    "🇵🇱 Ekstraklasa":      453,
    "🇸🇪 Allsvenskan":      573,
    "🇳🇴 Eliteserien":      444,
    "🇨🇭 Super League":     591,
    "🇺🇸 MLS":              779,
    "🇧🇷 Brasileirao":      648,
    "🇦🇷 Liga Profesional": 636,
}

POPULER_LIGLER = {
    "🇹🇷 Süper Lig":        600,
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier Lig":      8,
    "🇩🇪 Bundesliga":       82,
    "🇪🇸 La Liga":          564,
    "🇮🇹 Serie A":          384,
    "🇫🇷 Ligue 1":          301,
    "🇳🇱 Eredivisie":       72,
    "🇵🇹 Liga Portugal":    462,
    "🇧🇪 Pro League":       208,
    "🇹🇷 Türkiye Kupası":   606,
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 FA Cup":            24,
    "🇮🇹 Coppa Italia":     390,
    "🇪🇸 Copa Del Rey":     570,
    "🇧🇷 Brasileirao":      648,
    "🇦🇷 Liga Profesional": 636,
    "🇺🇸 MLS":              779,
}

TUMU = list(LIGLER.values())
POPULER_IDS = list(POPULER_LIGLER.values())

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# ── API ──────────────────────────────────────────────────────────────
class API:
    def __init__(self, token):
        self.token = token
        self.s = requests.Session()

    def get(self, endpoint, params=None):
        p = params or {}
        p["api_token"] = self.token
        try:
            r = self.s.get(f"{BASE_URL}/{endpoint}", params=p, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"API {endpoint}: {e}")
            return {}

    def maclar(self, tarih, lig_id=None):
        p = {"include": "participants;scores;state;league", "timezone": "Europe/Istanbul"}
        if lig_id:
            p["filters"] = f"fixtureLeagues:{lig_id}"
        return self.get(f"fixtures/date/{tarih}", p).get("data", [])

    def tum_maclar(self, tarih):
        lig_str = ",".join(str(i) for i in TUMU)
        p = {"include": "participants;scores;state;league", "timezone": "Europe/Istanbul",
             "filters": f"fixtureLeagues:{lig_str}"}
        return self.get(f"fixtures/date/{tarih}", p).get("data", [])

    def canli(self):
        p = {"include": "participants;scores;state;league"}
        return self.get("livescores/inplay", p).get("data", [])

    def puan(self, season_id):
        return self.get(f"standings/seasons/{season_id}",
                        {"include": "participant;details"}).get("data", [])

    def sezon(self, league_id):
        data = self.get(f"leagues/{league_id}", {"include": "currentSeason"}).get("data", {})
        s = data.get("currentSeason") or data.get("currentseason") or {}
        return s.get("id", 0)

    def h2h(self, t1, t2):
        return self.get(f"fixtures/head-to-head/{t1}/{t2}",
                        {"include": "participants;scores"}).get("data", [])

    def golkral(self, season_id):
        return self.get(f"topscorers/seasons/{season_id}",
                        {"include": "player;participant"}).get("data", [])

    def oyuncu_istat(self, season_id):
        return self.get(f"topscorers/seasons/{season_id}",
                        {"include": "player;participant;type"}).get("data", [])

    def mac_detay(self, fixture_id):
        return self.get(f"fixtures/{fixture_id}",
                        {"include": "participants;scores;events;statistics;lineups"}).get("data", {})


# ── YARDIMCI ─────────────────────────────────────────────────────────
def takim_adi(mac, konum):
    for p in mac.get("participants", []):
        if p.get("meta", {}).get("location") == konum:
            return p.get("name", "?")
    return "?"

def takim_id(mac, konum):
    for p in mac.get("participants", []):
        if p.get("meta", {}).get("location") == konum:
            return p.get("id", 0)
    return 0

def skor(mac):
    h = a = None
    for s in mac.get("scores", []):
        if s.get("description") == "CURRENT":
            sc = s.get("score", {})
            if sc.get("participant") == "home":
                h = sc.get("goals", 0)
            elif sc.get("participant") == "away":
                a = sc.get("goals", 0)
    return h, a

def durum(mac):
    st = mac.get("state", {})
    return st.get("short_name", "NS") if isinstance(st, dict) else "NS"

def saat_format(dt_str):
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return (dt + timedelta(hours=3)).strftime("%H:%M")
    except Exception:
        return "?"

def detay_parse(details):
    m = {129:"o", 130:"g", 131:"b", 132:"m", 133:"gf", 134:"ga", 179:"avg"}
    r = {}
    if isinstance(details, list):
        for item in details:
            k = m.get(item.get("type_id"))
            if k:
                r[k] = item.get("value", 0)
    return r

def lig_adi_bul(lig_id):
    tum = {**LIGLER, **POPULER_LIGLER}
    return next((a for a, i in tum.items() if i == lig_id), "Tüm Ligler")


# ── FORMAT ───────────────────────────────────────────────────────────
def mac_listesi_formatla(maclar, lig_adi="", baslik_prefix=""):
    if not maclar:
        isim = lig_adi if lig_adi else "Seçili liglerde"
        return "📭 " + isim + " için maç bulunamadı."

    tarih_str = datetime.now().strftime("%d.%m.%Y")
    if baslik_prefix:
        baslik = baslik_prefix
    elif lig_adi:
        baslik = "⚽ *" + lig_adi + " MAÇLARI*"
    else:
        baslik = "⚽ *BUGÜNÜN MAÇLARI*"

    mesaj = baslik + " (" + tarih_str + ")\n"
    mesaj += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

    gruplar = {}
    for mac in maclar:
        lo = mac.get("league", {})
        ln = lo.get("name", "Diğer") if isinstance(lo, dict) else "Diğer"
        gruplar.setdefault(ln, []).append(mac)

    for lig_name, lig_maclar in gruplar.items():
        if not lig_adi:
            mesaj += "🏆 *" + lig_name + "*\n"
        for mac in lig_maclar:
            ev = takim_adi(mac, "home")
            dep = takim_adi(mac, "away")
            d = durum(mac)
            sa = saat_format(mac.get("starting_at", ""))
            h, a = skor(mac)
            if d == "FT":
                mesaj += "   ✅ *" + ev + "* " + str(h) + "-" + str(a) + " *" + dep + "*\n"
            elif d in ["1H", "2H", "HT", "ET", "LIVE"]:
                mesaj += "   🔴 *" + ev + "* " + str(h) + "-" + str(a) + " *" + dep + "* _(" + d + ")_\n"
            else:
                mesaj += "   🕐 " + sa + " | " + ev + " - " + dep + "\n"
        mesaj += "\n"

    return mesaj.strip()


def puan_formatla(tablo, lig_adi):
    if not tablo:
        return "❌ Puan durumu alınamadı."
    mesaj = "📊 *" + lig_adi + " PUAN DURUMU*\n"
    mesaj += "━━━━━━━━━━━━━━━━━━━━━━\n"
    mesaj += "`#    Takım           O  G  B  M   P  Av`\n"
    for s in tablo[:18]:
        pos = s.get("position", 0)
        tn = s.get("participant", {}).get("name", "?")[:14].ljust(14)
        d = detay_parse(s.get("details", []))
        o = str(d.get("o", 0)).rjust(2)
        g = str(d.get("g", 0)).rjust(2)
        b = str(d.get("b", 0)).rjust(2)
        m = str(d.get("m", 0)).rjust(2)
        p = str(s.get("points", 0)).rjust(3)
        avg = d.get("avg", 0)
        av = ("+" + str(avg) if avg > 0 else str(avg)).rjust(3)
        em = "🏆" if pos <= 4 else ("🔴" if pos >= len(tablo) - 2 else "  ")
        mesaj += "`" + str(pos).rjust(2) + " " + em + tn + " " + o + " " + g + " " + b + " " + m + " " + p + " " + av + "`\n"
    return mesaj


# ── TAHMİN MOTORU (GELİŞTİRİLMİŞ) ───────────────────────────────────
def form_analiz(maclar, tkm_id):
    g = b = m = att = yedi = 0
    fs = ""
    for mac in maclar[-6:]:
        h, a = skor(mac)
        if h is None:
            continue
        ev_mi = any(p.get("id") == tkm_id and p.get("meta", {}).get("location") == "home"
                    for p in mac.get("participants", []))
        at_, ye_ = (h, a) if ev_mi else (a, h)
        att += at_ or 0
        yedi += ye_ or 0
        if at_ > ye_: g += 1; fs = "W" + fs
        elif at_ == ye_: b += 1; fs = "D" + fs
        else: m += 1; fs = "L" + fs
    top = g + b + m
    gol_ort = round(att / max(top, 1), 1)
    gol_yedi_ort = round(yedi / max(top, 1), 1)
    form_puan = round((g * 3 + b) / max(top * 3, 1) * 100, 1)
    return {
        "g": g, "b": b, "m": m, "att": att, "yedi": yedi,
        "gol_ort": gol_ort, "gol_yedi_ort": gol_yedi_ort,
        "fp": form_puan, "fs": fs[:5] or "?????"
    }

def h2h_analiz(maclar, ev_id):
    eg = dg = b = 0
    for mac in maclar[-8:]:
        h, a = skor(mac)
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
    return {"eg": eg, "dg": dg, "b": b, "top": eg + dg + b}

def tahmin_uret(ef, df, h2h=None):
    # Form puanı (0-100)
    ev_p = ef["fp"] + 10  # ev sahası avantajı
    dep_p = df["fp"]

    # H2H bonusu
    if h2h and h2h["top"] > 0:
        ev_p += (h2h["eg"] - h2h["dg"]) / h2h["top"] * 20

    # Gol ortalaması bonusu
    ev_p += ef["gol_ort"] * 4
    dep_p += df["gol_ort"] * 4

    # Savunma bonusu (az gol yiyen daha iyi)
    ev_p += max(0, (2 - ef["gol_yedi_ort"])) * 3
    dep_p += max(0, (2 - df["gol_yedi_ort"])) * 3

    fark = ev_p - dep_p

    # KG Var/Yok tahmini
    ort_gol = (ef["gol_ort"] + df["gol_ort"]) / 2
    kg_var = ort_gol >= 1.2

    # 2.5 üst/alt tahmini
    toplam_ort = ef["gol_ort"] + df["gol_ort"]
    ust_25 = toplam_ort >= 2.5

    if fark > 20: sonuc = "🏠 Ev Sahibi Kazanır"; guven = min(84, 64 + int(fark / 2))
    elif fark > 10: sonuc = "🏠 Ev / Beraberlik"; guven = 59
    elif fark < -20: sonuc = "✈️ Deplasman Kazanır"; guven = min(82, 62 + int(abs(fark) / 2))
    elif fark < -10: sonuc = "✈️ Dep / Beraberlik"; guven = 57
    else: sonuc = "🤝 Beraberlik"; guven = 54

    return sonuc, guven, kg_var, ust_25, round(toplam_ort, 1)


# ── BOT ──────────────────────────────────────────────────────────────
api = API(SPORTMONKS_TOKEN)
bildirimler = set()
sezon_cache = {}


def get_sezon(league_id):
    if league_id not in sezon_cache:
        sid = api.sezon(league_id)
        if sid:
            sezon_cache[league_id] = sid
    return sezon_cache.get(league_id, 0)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mesaj = (
        "⚽ *FUTBOL ANALİZ & TAHMİN BOTU*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🗓 /bugun \\- Bugünün maçları\n"
        "📅 /yarin \\- Yarının maçları\n"
        "✅ /sonuclar \\- Son maç sonuçları\n"
        "🔴 /canli \\- Canlı maçlar\n"
        "📊 /puan \\- Puan durumu\n"
        "🎯 /tahmin \\- Tahmin \\+ H2H analizi\n"
        "📈 /istatistik \\- Takım istatistikleri\n"
        "👤 /oyuncu \\- Oyuncu istatistikleri\n"
        "👑 /golkralligi \\- Gol krallığı\n"
        "🔔 /bildirim \\- Günlük bildirim\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Sportmonks API \\| 26 Lig"
    )
    await update.message.reply_text(mesaj, parse_mode="MarkdownV2")


async def cmd_bugun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(a, callback_data="bugun|" + str(i))] for a, i in POPULER_LIGLER.items()]
    kb.append([InlineKeyboardButton("🌍 Tüm Ligler", callback_data="bugun|0")])
    await update.message.reply_text(
        "🗓 *Bugün hangi ligin maçlarını görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def cmd_yarin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(a, callback_data="yarin|" + str(i))] for a, i in POPULER_LIGLER.items()]
    kb.append([InlineKeyboardButton("🌍 Tüm Ligler", callback_data="yarin|0")])
    await update.message.reply_text(
        "📅 *Yarın hangi ligin maçlarını görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def cmd_sonuclar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(a, callback_data="sonuc|" + str(i))] for a, i in POPULER_LIGLER.items()]
    kb.append([InlineKeyboardButton("🌍 Tüm Ligler", callback_data="sonuc|0")])
    await update.message.reply_text(
        "✅ *Hangi ligin son sonuçlarını görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def cmd_canli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Canlı maçlar yükleniyor...")
    maclar = api.canli()
    secili = [m for m in maclar if isinstance(m.get("league"), dict) and m["league"].get("id") in TUMU]
    goster = secili if secili else maclar[:20]
    if not goster:
        await update.message.reply_text("📭 Şu an canlı maç yok.")
        return
    mesaj = "🔴 *CANLI MAÇLAR* (" + str(len(goster)) + " maç)\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for mac in goster[:20]:
        ev = takim_adi(mac, "home")
        dep = takim_adi(mac, "away")
        h, a = skor(mac)
        lo = mac.get("league", {})
        lig = lo.get("name", "") if isinstance(lo, dict) else ""
        d = durum(mac)
        mesaj += "⚽ _" + lig + "_\n🔴 *" + ev + "* " + str(h) + "-" + str(a) + " *" + dep + "* _" + d + "_\n\n"
    await update.message.reply_text(mesaj, parse_mode="Markdown")


async def cmd_puan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(a, callback_data="puan|" + str(i))] for a, i in POPULER_LIGLER.items()]
    await update.message.reply_text(
        "📊 *Hangi ligin puan durumunu görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def cmd_tahmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(a, callback_data="tahmin|" + str(i))] for a, i in POPULER_LIGLER.items()]
    await update.message.reply_text(
        "🎯 *Hangi lig için tahmin almak istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def cmd_istatistik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(a, callback_data="istat|" + str(i))] for a, i in POPULER_LIGLER.items()]
    await update.message.reply_text(
        "📈 *Hangi ligin istatistiklerini görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def cmd_oyuncu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(a, callback_data="oyuncu|" + str(i))] for a, i in POPULER_LIGLER.items()]
    await update.message.reply_text(
        "👤 *Hangi ligin oyuncu istatistiklerini görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def cmd_golkralligi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(a, callback_data="golkral|" + str(i))] for a, i in POPULER_LIGLER.items()]
    await update.message.reply_text(
        "👑 *Hangi ligin gol krallığını görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def cmd_bildirim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in bildirimler:
        bildirimler.remove(uid)
        await update.message.reply_text("🔕 Bildirimler *kapatıldı*.", parse_mode="Markdown")
    else:
        bildirimler.add(uid)
        await update.message.reply_text(
            "🔔 Bildirimler *açıldı!* Her gün " + BILDIRIM_SAATI + "'de özet gelecek.",
            parse_mode="Markdown")


# ── BUTON HANDLER ────────────────────────────────────────────────────
async def btn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    islem, deger = q.data.split("|", 1)
    lig_id = int(deger)
    lig_adi = lig_adi_bul(lig_id)
    bugun = datetime.now().strftime("%Y-%m-%d")
    yarin = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    dun = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    if islem == "bugun":
        await q.edit_message_text("⏳ Maçlar yükleniyor...")
        maclar = api.tum_maclar(bugun) if lig_id == 0 else api.maclar(bugun, lig_id)
        await q.edit_message_text(mac_listesi_formatla(maclar, lig_adi), parse_mode="Markdown")

    elif islem == "yarin":
        await q.edit_message_text("⏳ Yarının maçları yükleniyor...")
        maclar = api.tum_maclar(yarin) if lig_id == 0 else api.maclar(yarin, lig_id)
        yarin_str = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
        mesaj = mac_listesi_formatla(maclar, lig_adi, "📅 *" + lig_adi + " YARIN* (" + yarin_str + ")")
        await q.edit_message_text(mesaj, parse_mode="Markdown")

    elif islem == "sonuc":
        await q.edit_message_text("⏳ Son sonuçlar yükleniyor...")
        # Dün + bugün bitmiş maçlar
        maclar_dun = api.tum_maclar(dun) if lig_id == 0 else api.maclar(dun, lig_id)
        maclar_bugun = api.tum_maclar(bugun) if lig_id == 0 else api.maclar(bugun, lig_id)
        bitmis = [m for m in maclar_dun + maclar_bugun if durum(m) == "FT"]
        if not bitmis:
            await q.edit_message_text("📭 Son 2 günde bitmiş maç bulunamadı.")
            return
        dun_str = (datetime.now() - timedelta(days=1)).strftime("%d.%m.%Y")
        mesaj = "✅ *" + lig_adi + " SON SONUÇLAR*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        gruplar = {}
        for mac in bitmis:
            lo = mac.get("league", {})
            ln = lo.get("name", "?") if isinstance(lo, dict) else "?"
            gruplar.setdefault(ln, []).append(mac)
        for ln, lm in gruplar.items():
            if lig_id == 0:
                mesaj += "🏆 *" + ln + "*\n"
            for mac in lm:
                ev = takim_adi(mac, "home")
                dep = takim_adi(mac, "away")
                h, a = skor(mac)
                mesaj += "   ✅ *" + ev + "* " + str(h) + " - " + str(a) + " *" + dep + "*\n"
            mesaj += "\n"
        await q.edit_message_text(mesaj, parse_mode="Markdown")

    elif islem == "puan":
        await q.edit_message_text("⏳ Puan durumu yükleniyor...")
        sid = get_sezon(lig_id)
        if not sid:
            await q.edit_message_text("❌ Sezon bilgisi alınamadı.")
            return
        tablo = api.puan(sid)
        await q.edit_message_text(puan_formatla(tablo, lig_adi), parse_mode="Markdown")

    elif islem == "tahmin":
        await q.edit_message_text("⏳ Tahminler hesaplanıyor...")
        maclar = api.maclar(bugun, lig_id)
        if not maclar:
            maclar = api.maclar(yarin, lig_id)
            if not maclar:
                await q.edit_message_text("📭 " + lig_adi + " için yakında maç bulunamadı.")
                return
        tarih_str = datetime.now().strftime("%d.%m.%Y")
        mesaj = "🎯 *" + lig_adi + " TAHMİNLERİ*\n📅 " + tarih_str + "\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for mac in maclar[:5]:
            ev = takim_adi(mac, "home")
            dep = takim_adi(mac, "away")
            eid = takim_id(mac, "home")
            did = takim_id(mac, "away")
            sa = saat_format(mac.get("starting_at", ""))
            h2h_m = api.h2h(eid, did) if eid and did else []
            h2hd = h2h_analiz(h2h_m, eid)
            ef = form_analiz(h2h_m, eid)
            df = form_analiz(h2h_m, did)
            sonuc, guven, kg_var, ust_25, gol_ort = tahmin_uret(ef, df, h2hd)
            cubuk = "█" * int(guven / 10) + "░" * (10 - int(guven / 10))
            mesaj += "⚔️ *" + ev + "* vs *" + dep + "*\n"
            mesaj += "   🕐 " + sa + "\n"
            mesaj += "   🏠 Form: `" + ef["fs"] + "` | " + str(ef["gol_ort"]) + " gol/maç\n"
            mesaj += "   ✈️ Form: `" + df["fs"] + "` | " + str(df["gol_ort"]) + " gol/maç\n"
            if h2hd["top"] > 0:
                mesaj += "   ⚔️ H2H (" + str(h2hd["top"]) + " maç): " + str(h2hd["eg"]) + "G " + str(h2hd["b"]) + "B " + str(h2hd["dg"]) + "M\n"
            mesaj += "   💡 *" + sonuc + "*\n"
            mesaj += "   📈 [" + cubuk + "] %" + str(guven) + "\n"
            mesaj += "   ⚽ Beklenen gol: ~" + str(gol_ort) + " | "
            mesaj += ("2.5 Üst" if ust_25 else "2.5 Alt") + " | "
            mesaj += ("KG Var" if kg_var else "KG Yok") + "\n\n"
        mesaj += "⚠️ _Form, H2H ve gol ortalamasına dayanır._"
        await q.edit_message_text(mesaj, parse_mode="Markdown")

    elif islem == "istat":
        await q.edit_message_text("⏳ İstatistikler yükleniyor...")
        sid = get_sezon(lig_id)
        if not sid:
            await q.edit_message_text("❌ Sezon bilgisi alınamadı.")
            return
        tablo = api.puan(sid)
        if not tablo:
            await q.edit_message_text("❌ Veri alınamadı.")
            return
        mesaj = "📈 *" + lig_adi + " TAKIM İSTATİSTİKLERİ*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for s in tablo[:12]:
            tkm = s.get("participant", {}).get("name", "?")
            pos = s.get("position", "?")
            p = s.get("points", 0)
            d = detay_parse(s.get("details", []))
            o = d.get("o", 0); g = d.get("g", 0); b = d.get("b", 0); m = d.get("m", 0)
            gf = d.get("gf", 0); ga = d.get("ga", 0); avg = d.get("avg", 0)
            avg_s = ("+" + str(avg)) if avg > 0 else str(avg)
            gol_ort_s = str(round(gf / max(o, 1), 1))
            em = "🏆" if pos <= 4 else ("🔴" if pos >= 15 else "🔵")
            mesaj += em + " *" + str(pos) + ". " + tkm + "* — " + str(p) + " puan\n"
            mesaj += "   " + str(o) + " maç | " + str(g) + "G " + str(b) + "B " + str(m) + "M\n"
            mesaj += "   ⚽ " + str(gf) + " gol (" + gol_ort_s + "/maç) | " + str(ga) + " yenilen | Av: " + avg_s + "\n\n"
        await q.edit_message_text(mesaj, parse_mode="Markdown")

    elif islem == "oyuncu":
        await q.edit_message_text("⏳ Oyuncu istatistikleri yükleniyor...")
        sid = get_sezon(lig_id)
        if not sid:
            await q.edit_message_text("❌ Sezon bilgisi alınamadı.")
            return
        liste = api.oyuncu_istat(sid)
        if not liste:
            await q.edit_message_text("❌ Veri alınamadı.")
            return
        mesaj = "👤 *" + lig_adi + " OYUNCU İSTATİSTİKLERİ*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        mesaj += "👑 *En Çok Gol Atanlar*\n"
        madalya = ["🥇", "🥈", "🥉"]
        for i, s in enumerate(liste[:10], 1):
            oyuncu = s.get("player", {}).get("name", "?") if isinstance(s.get("player"), dict) else "?"
            tkm = s.get("participant", {}).get("name", "?") if isinstance(s.get("participant"), dict) else "?"
            gol = s.get("total", "?")
            icon = madalya[i-1] if i <= 3 else str(i) + "."
            mesaj += icon + " *" + oyuncu + "* — " + str(gol) + " ⚽\n"
            mesaj += "   _" + tkm + "_\n"
        await q.edit_message_text(mesaj, parse_mode="Markdown")

    elif islem == "golkral":
        await q.edit_message_text("⏳ Gol krallığı yükleniyor...")
        sid = get_sezon(lig_id)
        if not sid:
            await q.edit_message_text("❌ Sezon bilgisi alınamadı.")
            return
        liste = api.golkral(sid)
        if not liste:
            await q.edit_message_text("❌ Veri alınamadı.")
            return
        mesaj = "👑 *" + lig_adi + " GOL KRALLIGI*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        madalya = ["🥇", "🥈", "🥉"]
        for i, s in enumerate(liste[:15], 1):
            oyuncu = s.get("player", {}).get("name", "?") if isinstance(s.get("player"), dict) else "?"
            tkm = s.get("participant", {}).get("name", "?") if isinstance(s.get("participant"), dict) else "?"
            gol = s.get("total", "?")
            icon = madalya[i-1] if i <= 3 else str(i) + "."
            mesaj += icon + " *" + oyuncu + "* — " + str(gol) + " ⚽\n   _" + tkm + "_\n\n"
        await q.edit_message_text(mesaj, parse_mode="Markdown")


async def gunluk(context: ContextTypes.DEFAULT_TYPE):
    if not bildirimler:
        return
    bugun = datetime.now().strftime("%Y-%m-%d")
    tarih_str = datetime.now().strftime("%d.%m.%Y")
    maclar = api.tum_maclar(bugun)
    mesaj = "🌅 *GÜNLÜK FUTBOL BÜLTENİ* — " + tarih_str + "\n\n"
    mesaj += mac_listesi_formatla(maclar)
    for uid in bildirimler.copy():
        try:
            await context.bot.send_message(chat_id=uid, text=mesaj, parse_mode="Markdown")
        except Exception:
            bildirimler.discard(uid)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("bugun", cmd_bugun))
    app.add_handler(CommandHandler("yarin", cmd_yarin))
    app.add_handler(CommandHandler("sonuclar", cmd_sonuclar))
    app.add_handler(CommandHandler("canli", cmd_canli))
    app.add_handler(CommandHandler("puan", cmd_puan))
    app.add_handler(CommandHandler("tahmin", cmd_tahmin))
    app.add_handler(CommandHandler("istatistik", cmd_istatistik))
    app.add_handler(CommandHandler("oyuncu", cmd_oyuncu))
    app.add_handler(CommandHandler("golkralligi", cmd_golkralligi))
    app.add_handler(CommandHandler("bildirim", cmd_bildirim))
    app.add_handler(CallbackQueryHandler(btn_handler))
    saat, dakika = map(int, BILDIRIM_SAATI.split(":"))
    app.job_queue.run_daily(
        gunluk,
        time=datetime.now().replace(hour=saat, minute=dakika, second=0).time()
    )
    logger.info("Futbol Bot v5 basladi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
