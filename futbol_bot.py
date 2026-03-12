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
    "🇹🇷 Süper Lig":       600,
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier Lig":     8,
    "🇩🇪 Bundesliga":      82,
    "🇪🇸 La Liga":         564,
    "🇮🇹 Serie A":         384,
    "🇫🇷 Ligue 1":         301,
    "🇳🇱 Eredivisie":      72,
    "🇵🇹 Liga Portugal":   462,
    "🇧🇪 Pro League":      208,
    "🏆 Şampiyonlar Ligi": 2,
    "🌍 Avrupa Ligi":      5,
    "🇹🇷 Türkiye Kupası":  606,
}

TUMU = list(LIGLER.values())
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


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
        return self.get(f"standings/seasons/{season_id}", {"include": "participant;details"}).get("data", [])

    def sezon(self, league_id):
        data = self.get(f"leagues/{league_id}", {"include": "currentSeason"}).get("data", {})
        s = data.get("currentSeason") or data.get("currentseason") or {}
        return s.get("id", 0)

    def h2h(self, t1, t2):
        return self.get(f"fixtures/head-to-head/{t1}/{t2}", {"include": "participants;scores"}).get("data", [])

    def golkral(self, season_id):
        return self.get(f"topscorers/seasons/{season_id}", {"include": "player;participant"}).get("data", [])


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
    # 129=oynanan 130=galibiyet 131=beraberlik 132=maglubiyet 133=gol_atti 134=gol_yedi 179=averaj
    m = {129:"o", 130:"g", 131:"b", 132:"m", 133:"gf", 134:"ga", 179:"avg"}
    r = {}
    if isinstance(details, list):
        for item in details:
            k = m.get(item.get("type_id"))
            if k:
                r[k] = item.get("value", 0)
    return r


def mac_listesi_formatla(maclar, lig_adi=""):
    if not maclar:
        isim = lig_adi if lig_adi else "Seçili liglerde"
        return f"📭 {isim} için bugün maç bulunamadı."

    tarih_str = datetime.now().strftime("%d.%m.%Y")
    baslik = f"⚽ *{lig_adi} MAÇLARI*" if lig_adi else "⚽ *BUGÜNÜN MAÇLARI*"
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
                mesaj += "   🔴 *" + ev + "* " + str(h) + "-" + str(a) + " *" + dep + "* _" + d + "_\n"
            else:
                mesaj += "   🕐 " + sa + " | " + ev + " vs " + dep + "\n"
        mesaj += "\n"

    return mesaj.strip()


def puan_formatla(tablo, lig_adi):
    if not tablo:
        return "❌ Puan durumu alınamadı."
    mesaj = "📊 *" + lig_adi + " PUAN DURUMU*\n"
    mesaj += "━━━━━━━━━━━━━━━━━━━━━━\n"
    mesaj += "`#   Takım            O  G  B  M   P  Av`\n"
    for s in tablo[:18]:
        pos = s.get("position", 0)
        takimadi = s.get("participant", {}).get("name", "?")[:13].ljust(13)
        d = detay_parse(s.get("details", []))
        o = str(d.get("o", 0)).rjust(2)
        g = str(d.get("g", 0)).rjust(2)
        b = str(d.get("b", 0)).rjust(2)
        m = str(d.get("m", 0)).rjust(2)
        p = str(s.get("points", 0)).rjust(3)
        avg = d.get("avg", 0)
        avg_s = ("+" + str(avg) if avg > 0 else str(avg)).rjust(3)
        em = "🏆" if pos <= 4 else ("🔴" if pos >= len(tablo) - 2 else "  ")
        mesaj += "`" + str(pos).rjust(2) + " " + em + takimadi + " " + o + " " + g + " " + b + " " + m + " " + p + " " + avg_s + "`\n"
    return mesaj


# Tahmin
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
    return {"g": g, "b": b, "m": m, "att": att, "yedi": yedi,
            "fp": round((g*3+b) / max(top*3,1) * 100, 1),
            "fs": fs[:5] or "?????"}

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
    return {"eg": eg, "dg": dg, "b": b, "top": eg+dg+b}

def tahmin_uret(ef, df, h2h=None):
    ev_p = ef["fp"] + 10
    dep_p = df["fp"]
    if h2h and h2h["top"] > 0:
        ev_p += (h2h["eg"] - h2h["dg"]) / h2h["top"] * 15
    ev_p += ef["att"] / max(ef["g"]+ef["b"]+ef["m"], 1) * 3
    dep_p += df["att"] / max(df["g"]+df["b"]+df["m"], 1) * 3
    fark = ev_p - dep_p
    if fark > 18: return "🏠 Ev Sahibi Kazanır", min(83, 62+int(fark/2))
    elif fark > 8: return "🏠 Ev / Beraberlik", 57
    elif fark < -18: return "✈️ Deplasman Kazanır", min(81, 60+int(abs(fark)/2))
    elif fark < -8: return "✈️ Dep / Beraberlik", 55
    else: return "🤝 Beraberlik", 53


# Bot globals
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
    await update.message.reply_text(
        "⚽ *FUTBOL ANALİZ & TAHMİN BOTUNA HOŞGELDİN!*\n\n"
        "📌 *Komutlar:*\n\n"
        "🗓 /bugun \\- Bugünün maçları\n"
        "🔴 /canli \\- Canlı maçlar\n"
        "📊 /puan \\- Puan durumu\n"
        "🎯 /tahmin \\- Maç tahminleri \\+ H2H\n"
        "📈 /istatistik \\- Takım istatistikleri\n"
        "👑 /golkralligi \\- Gol krallığı\n"
        "🔔 /bildirim \\- Günlük bildirim\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Sportmonks API \\| 2500\\+ Lig",
        parse_mode="MarkdownV2"
    )


async def cmd_bugun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(a, callback_data="bugun|" + str(i))] for a, i in LIGLER.items()]
    kb.append([InlineKeyboardButton("🌍 Tüm Seçili Ligler", callback_data="bugun|0")])
    await update.message.reply_text(
        "🗓 *Hangi ligin maçlarını görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def cmd_canli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Canlı maçlar yükleniyor...")
    maclar = api.canli()
    secili = [m for m in maclar if isinstance(m.get("league"), dict) and m["league"].get("id") in TUMU]
    goster = secili if secili else maclar[:15]
    if not goster:
        await update.message.reply_text("📭 Şu an canlı maç yok.")
        return
    mesaj = "🔴 *CANLI MAÇLAR* (" + str(len(goster)) + " maç)\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for mac in goster[:15]:
        ev = takim_adi(mac, "home")
        dep = takim_adi(mac, "away")
        h, a = skor(mac)
        lo = mac.get("league", {})
        lig = lo.get("name", "") if isinstance(lo, dict) else ""
        d = durum(mac)
        mesaj += "⚽ _" + lig + "_\n🔴 *" + ev + "* " + str(h) + "-" + str(a) + " *" + dep + "* _" + d + "_\n\n"
    await update.message.reply_text(mesaj, parse_mode="Markdown")


async def cmd_puan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(a, callback_data="puan|" + str(i))] for a, i in LIGLER.items()]
    await update.message.reply_text(
        "📊 *Hangi ligin puan durumunu görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def cmd_tahmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(a, callback_data="tahmin|" + str(i))] for a, i in LIGLER.items()]
    await update.message.reply_text(
        "🎯 *Hangi lig için tahmin almak istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def cmd_istatistik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(a, callback_data="istat|" + str(i))] for a, i in LIGLER.items()]
    await update.message.reply_text(
        "📈 *Hangi ligin istatistiklerini görmek istiyorsun?*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def cmd_golkralligi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(a, callback_data="golkral|" + str(i))] for a, i in LIGLER.items()]
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


async def btn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    islem, deger = q.data.split("|", 1)
    lig_id = int(deger)
    lig_adi = next((a for a, i in LIGLER.items() if i == lig_id), "Tüm Ligler")
    tarih = datetime.now().strftime("%Y-%m-%d")

    if islem == "bugun":
        await q.edit_message_text("⏳ Maçlar yükleniyor...")
        maclar = api.tum_maclar(tarih) if lig_id == 0 else api.maclar(tarih, lig_id)
        await q.edit_message_text(mac_listesi_formatla(maclar, lig_adi), parse_mode="Markdown")

    elif islem == "puan":
        await q.edit_message_text("⏳ Puan durumu yükleniyor...")
        sid = get_sezon(lig_id)
        if not sid:
            await q.edit_message_text("❌ Sezon bilgisi alınamadı.")
            return
        tablo = api.puan(sid)
        await q.edit_message_text(puan_formatla(tablo, lig_adi), parse_mode="Markdown")

    elif islem == "tahmin":
        await q.edit_message_text("⏳ Tahminler hazırlanıyor...")
        maclar = api.maclar(tarih, lig_id)
        if not maclar:
            await q.edit_message_text("📭 " + lig_adi + " için bugün maç yok.")
            return
        tarih_str = datetime.now().strftime("%d.%m.%Y")
        mesaj = "🎯 *" + lig_adi + " TAHMİNLERİ*\n📅 " + tarih_str + "\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for mac in maclar[:4]:
            ev = takim_adi(mac, "home")
            dep = takim_adi(mac, "away")
            eid = takim_id(mac, "home")
            did = takim_id(mac, "away")
            sa = saat_format(mac.get("starting_at", ""))
            h2h_m = api.h2h(eid, did) if eid and did else []
            h2hd = h2h_analiz(h2h_m, eid)
            ef = form_analiz(h2h_m, eid)
            df = form_analiz(h2h_m, did)
            sonuc, guven = tahmin_uret(ef, df, h2hd)
            cubuk = "█" * int(guven/10) + "░" * (10 - int(guven/10))
            mesaj += "⚔️ *" + ev + "* vs *" + dep + "*\n"
            mesaj += "   🕐 " + sa + "\n"
            mesaj += "   🏠 Form: `" + ef["fs"] + "` (" + str(ef["g"]) + "G " + str(ef["b"]) + "B " + str(ef["m"]) + "M)\n"
            mesaj += "   ✈️ Form: `" + df["fs"] + "` (" + str(df["g"]) + "G " + str(df["b"]) + "B " + str(df["m"]) + "M)\n"
            if h2hd["top"] > 0:
                mesaj += "   ⚔️ H2H: " + str(h2hd["eg"]) + "G " + str(h2hd["b"]) + "B " + str(h2hd["dg"]) + "M\n"
            mesaj += "   💡 *" + sonuc + "*\n"
            mesaj += "   📈 [" + cubuk + "] %" + str(guven) + "\n\n"
        mesaj += "⚠️ _Form ve H2H analizine dayanır._"
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
        mesaj = "📈 *" + lig_adi + " İSTATİSTİKLER*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for s in tablo[:12]:
            tkm = s.get("participant", {}).get("name", "?")
            pos = s.get("position", "?")
            p = s.get("points", 0)
            d = detay_parse(s.get("details", []))
            o = d.get("o", 0); g = d.get("g", 0); b = d.get("b", 0); m = d.get("m", 0)
            gf = d.get("gf", "?"); ga = d.get("ga", "?"); avg = d.get("avg", 0)
            avg_s = ("+" + str(avg)) if avg > 0 else str(avg)
            em = "🏆" if pos <= 4 else ("🔴" if pos >= 16 else "🔵")
            mesaj += em + " *" + str(pos) + ". " + tkm + "* — " + str(p) + " puan\n"
            mesaj += "   " + str(o) + " maç: " + str(g) + "G " + str(b) + "B " + str(m) + "M\n"
            mesaj += "   ⚽ " + str(gf) + " attı / " + str(ga) + " yedi | Av: " + avg_s + "\n\n"
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
        for i, s in enumerate(liste[:10], 1):
            oyuncu = s.get("player", {}).get("name", "?") if isinstance(s.get("player"), dict) else "?"
            tkm = s.get("participant", {}).get("name", "?") if isinstance(s.get("participant"), dict) else "?"
            gol = s.get("total", "?")
            icon = madalya[i-1] if i <= 3 else str(i) + "."
            mesaj += icon + " *" + oyuncu + "* — " + str(gol) + " ⚽\n   _" + tkm + "_\n\n"
        await q.edit_message_text(mesaj, parse_mode="Markdown")


async def gunluk(context: ContextTypes.DEFAULT_TYPE):
    if not bildirimler:
        return
    tarih = datetime.now().strftime("%Y-%m-%d")
    maclar = api.tum_maclar(tarih)
    tarih_str = datetime.now().strftime("%d.%m.%Y")
    mesaj = "🌅 *GÜNLÜK FUTBOL BÜLTENİ* - " + tarih_str + "\n\n" + mac_listesi_formatla(maclar)
    for uid in bildirimler.copy():
        try:
            await context.bot.send_message(chat_id=uid, text=mesaj, parse_mode="Markdown")
        except Exception:
            bildirimler.discard(uid)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("bugun", cmd_bugun))
    app.add_handler(CommandHandler("canli", cmd_canli))
    app.add_handler(CommandHandler("puan", cmd_puan))
    app.add_handler(CommandHandler("tahmin", cmd_tahmin))
    app.add_handler(CommandHandler("istatistik", cmd_istatistik))
    app.add_handler(CommandHandler("golkralligi", cmd_golkralligi))
    app.add_handler(CommandHandler("bildirim", cmd_bildirim))
    app.add_handler(CallbackQueryHandler(btn_handler))
    saat, dakika = map(int, BILDIRIM_SAATI.split(":"))
    app.job_queue.run_daily(
        gunluk,
        time=datetime.now().replace(hour=saat, minute=dakika, second=0).time()
    )
    logger.info("Futbol Bot v4 basladi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
