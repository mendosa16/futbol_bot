#!/usr/bin/env python3
"""
⚽ Futbol Tahmin Telegram Botu
- Football-Data.org ücretsiz API kullanır
- Günlük maç tahminleri
- İstatistik analizi
- Otomatik günlük bildirim
"""

import os
import logging
import asyncio
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
TELEGRAM_TOKEN = "8610318322:AAE8ylN7txpmro21b74ca1XvNQY6taBATec"
FOOTBALL_API_KEY = "03ac61b2f4f644b59923776bd31702e3"
BILDIRIM_SAATI = "08:00"  # Günlük bildirim saati (HH:MM)

# Takip edilecek ligler (Football-Data.org kodları)
LIGLER = {
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier Lig": "PL",
    "🇩🇪 Bundesliga": "BL1",
    "🇪🇸 La Liga": "PD",
    "🇮🇹 Serie A": "SA",
    "🇫🇷 Ligue 1": "FL1",
    "🇹🇷 Süper Lig": "TSL",  # Not: Ücretsiz planda olmayabilir
    "🏆 Şampiyonlar Ligi": "CL",
}

# ===================== LOGGING =====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== API SINIFI =====================
class FootballAPI:
    BASE_URL = "https://api.football-data.org/v4"

    def __init__(self, api_key: str):
        self.headers = {"X-Auth-Token": api_key}

    def get_matches(self, tarih: str = None, lig_kodu: str = None) -> dict:
        """Belirli bir tarihteki maçları çeker."""
        if tarih is None:
            tarih = datetime.now().strftime("%Y-%m-%d")

        url = f"{self.BASE_URL}/matches"
        params = {"date": tarih}
        if lig_kodu:
            url = f"{self.BASE_URL}/competitions/{lig_kodu}/matches"
            params["dateFrom"] = tarih
            params["dateTo"] = tarih

        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"API hatası: {e}")
            return {}

    def get_standings(self, lig_kodu: str) -> dict:
        """Lig puan durumunu çeker."""
        url = f"{self.BASE_URL}/competitions/{lig_kodu}/standings"
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Puan durumu hatası: {e}")
            return {}

    def get_team_stats(self, takim_id: int) -> dict:
        """Takım istatistiklerini çeker."""
        url = f"{self.BASE_URL}/teams/{takim_id}/matches"
        params = {"limit": 10, "status": "FINISHED"}
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Takım istatistik hatası: {e}")
            return {}


# ===================== TAHMİN MOTORU =====================
class TahminMotoru:
    """Basit istatistik tabanlı tahmin sistemi."""

    @staticmethod
    def son_form_analiz(maclar: list, takim_id: int) -> dict:
        """Son 5 maçtaki form analizi."""
        galibiyet = beraberlik = maglubiyet = 0
        atilan = yenilen = 0

        for mac in maclar[-5:]:
            ev = mac.get("homeTeam", {}).get("id") == takim_id
            ev_gol = mac.get("score", {}).get("fullTime", {}).get("home", 0) or 0
            dep_gol = mac.get("score", {}).get("fullTime", {}).get("away", 0) or 0

            if ev:
                atilan += ev_gol
                yenilen += dep_gol
                if ev_gol > dep_gol:
                    galibiyet += 1
                elif ev_gol == dep_gol:
                    beraberlik += 1
                else:
                    maglubiyet += 1
            else:
                atilan += dep_gol
                yenilen += ev_gol
                if dep_gol > ev_gol:
                    galibiyet += 1
                elif dep_gol == ev_gol:
                    beraberlik += 1
                else:
                    maglubiyet += 1

        toplam = galibiyet + beraberlik + maglubiyet
        form_puani = (galibiyet * 3 + beraberlik) / max(toplam * 3, 1) * 100

        return {
            "galibiyet": galibiyet,
            "beraberlik": beraberlik,
            "maglubiyet": maglubiyet,
            "atilan": atilan,
            "yenilen": yenilen,
            "form_puani": round(form_puani, 1),
        }

    @staticmethod
    def mac_tahmini(ev_formu: dict, dep_formu: dict) -> str:
        """Form verilerine göre maç tahmini üretir."""
        ev_puan = ev_formu["form_puani"]
        dep_puan = dep_formu["form_puani"]

        # Ev sahibi avantajı (+10 puan)
        ev_puan_ayarli = ev_puan + 10

        fark = ev_puan_ayarli - dep_puan

        if fark > 20:
            tahmin = "🏠 Ev Sahibi Kazanır"
            guven = min(85, 60 + int(fark / 2))
        elif fark > 8:
            tahmin = "🏠 Ev Sahibi Kazanır / Beraberlik"
            guven = 55
        elif fark < -20:
            tahmin = "✈️ Deplasman Kazanır"
            guven = min(80, 60 + int(abs(fark) / 2))
        elif fark < -8:
            tahmin = "✈️ Deplasman Kazanır / Beraberlik"
            guven = 55
        else:
            tahmin = "🤝 Beraberlik / Her İki Takım da Kazanabilir"
            guven = 50

        return tahmin, guven


# ===================== MESAJ FORMATLARI =====================
def format_mac_listesi(maclar: list) -> str:
    """Maç listesini güzel formatta döndürür."""
    if not maclar:
        return "📭 Bugün için maç bulunamadı."

    mesaj = f"⚽ *BUGÜNÜN MAÇLARI* ({datetime.now().strftime('%d.%m.%Y')})\n"
    mesaj += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for mac in maclar[:15]:  # Max 15 maç göster
        ev = mac.get("homeTeam", {}).get("shortName", "?")
        dep = mac.get("awayTeam", {}).get("shortName", "?")
        durum = mac.get("status", "")
        utc_time = mac.get("utcDate", "")

        # Saati Türkiye saatine çevir (UTC+3)
        try:
            mac_dt = datetime.strptime(utc_time, "%Y-%m-%dT%H:%M:%SZ")
            mac_dt = mac_dt + timedelta(hours=3)
            saat = mac_dt.strftime("%H:%M")
        except:
            saat = "?"

        if durum == "FINISHED":
            ev_gol = mac.get("score", {}).get("fullTime", {}).get("home", "-")
            dep_gol = mac.get("score", {}).get("fullTime", {}).get("away", "-")
            mesaj += f"✅ {ev} *{ev_gol} - {dep_gol}* {dep}\n"
        elif durum == "IN_PLAY":
            mesaj += f"🔴 CANLI: {ev} vs {dep}\n"
        else:
            mesaj += f"🕐 {saat} | {ev} vs {dep}\n"

    mesaj += "\n💡 /tahmin - Detaylı analiz al"
    return mesaj


def format_puan_durumu(standings_data: dict, lig_adi: str) -> str:
    """Puan durumunu formatlı döndürür."""
    try:
        tablo = standings_data["standings"][0]["table"]
    except:
        return "❌ Puan durumu alınamadı."

    mesaj = f"📊 *{lig_adi} PUAN DURUMU*\n"
    mesaj += "━━━━━━━━━━━━━━━━━━━━━━\n"
    mesaj += "`#  Takım           O   G   B   M   P`\n"

    for satir in tablo[:10]:
        pos = satir.get("position", "?")
        takim = satir.get("team", {}).get("shortName", "?")[:12].ljust(12)
        o = satir.get("playedGames", 0)
        g = satir.get("won", 0)
        b = satir.get("draw", 0)
        m = satir.get("lost", 0)
        p = satir.get("points", 0)

        # İlk 4 = Şampiyonlar Ligi, son 3 = Küme düşme
        emoji = "🏆" if pos <= 4 else ("🔴" if pos >= len(tablo) - 2 else "  ")
        mesaj += f"`{str(pos).rjust(2)} {emoji}{takim} {str(o).rjust(2)} {str(g).rjust(2)} {str(b).rjust(2)} {str(m).rjust(2)} {str(p).rjust(3)}`\n"

    return mesaj


# ===================== BOT KOMUTLARI =====================
api = FootballAPI(FOOTBALL_API_KEY)
tahmin_motoru = TahminMotoru()

# Bildirim listesi (kullanıcı ID'leri)
bildirim_listesi: set = set()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot başlangıç komutu."""
    mesaj = (
        "⚽ *FUTBOL TAHMİN BOTUNA HOŞGELDİN!*\n\n"
        "📌 *Kullanılabilir komutlar:*\n\n"
        "🗓 /bugun - Bugünün maçları\n"
        "📊 /puan - Puan durumu\n"
        "🎯 /tahmin - Maç tahminleri\n"
        "🔔 /bildirim - Günlük bildirim aç/kapat\n"
        "ℹ️ /hakkinda - Bot hakkında\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Her gün saat 08:00'de otomatik maç özeti gönderilir!"
    )
    await update.message.reply_text(mesaj, parse_mode="Markdown")


async def bugun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bugünün maçlarını gösterir."""
    await update.message.reply_text("⏳ Maçlar yükleniyor...", parse_mode="Markdown")

    data = api.get_matches()
    maclar = data.get("matches", [])

    mesaj = format_mac_listesi(maclar)
    await update.message.reply_text(mesaj, parse_mode="Markdown")


async def puan_durumu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lig seçim menüsü gösterir."""
    keyboard = []
    for lig_adi, lig_kodu in list(LIGLER.items())[:6]:
        keyboard.append([InlineKeyboardButton(lig_adi, callback_data=f"puan_{lig_kodu}_{lig_adi}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📊 *Hangi ligin puan durumunu görmek istiyorsun?*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def tahmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lig seçim menüsü gösterir (tahmin için)."""
    keyboard = []
    for lig_adi, lig_kodu in list(LIGLER.items())[:6]:
        keyboard.append([InlineKeyboardButton(lig_adi, callback_data=f"tahmin_{lig_kodu}_{lig_adi}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎯 *Hangi lig için tahmin almak istiyorsun?*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def bildirim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Günlük bildirimi aç/kapat."""
    user_id = update.effective_user.id

    if user_id in bildirim_listesi:
        bildirim_listesi.remove(user_id)
        await update.message.reply_text(
            "🔕 Günlük bildirimler *kapatıldı*.\n\n"
            "Tekrar açmak için /bildirim yaz.",
            parse_mode="Markdown"
        )
    else:
        bildirim_listesi.add(user_id)
        await update.message.reply_text(
            f"🔔 Günlük bildirimler *açıldı!*\n\n"
            f"Her gün saat {BILDIRIM_SAATI}'de maç özetini alacaksın.",
            parse_mode="Markdown"
        )


async def hakkinda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot hakkında bilgi."""
    mesaj = (
        "ℹ️ *FUTBOL TAHMİN BOTU*\n\n"
        "📡 Veri kaynağı: football-data.org\n"
        "🤖 Tahmin motoru: Form analizi + Ev sahibi avantajı\n\n"
        "⚠️ *Uyarı:* Tahminler %100 kesin değildir. "
        "Sadece istatistiksel analize dayanır.\n\n"
        "🆕 Veriler her maç öncesi güncellenir."
    )
    await update.message.reply_text(mesaj, parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline buton işleyicisi."""
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split("_", 2)
    islem = parts[0]
    lig_kodu = parts[1]
    lig_adi = parts[2] if len(parts) > 2 else lig_kodu

    if islem == "puan":
        await query.edit_message_text("⏳ Puan durumu yükleniyor...")
        standings = api.get_standings(lig_kodu)
        mesaj = format_puan_durumu(standings, lig_adi)
        await query.edit_message_text(mesaj, parse_mode="Markdown")

    elif islem == "tahmin":
        await query.edit_message_text("⏳ Tahminler hesaplanıyor...")
        tarih = datetime.now().strftime("%Y-%m-%d")
        data_mac = api.get_matches(tarih=tarih, lig_kodu=lig_kodu)
        maclar = data_mac.get("matches", [])

        if not maclar:
            await query.edit_message_text(
                f"📭 {lig_adi} için bugün maç bulunamadı."
            )
            return

        mesaj = f"🎯 *{lig_adi} TAHMİNLERİ*\n"
        mesaj += f"📅 {datetime.now().strftime('%d.%m.%Y')}\n"
        mesaj += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

        for mac in maclar[:5]:
            ev_takim = mac.get("homeTeam", {})
            dep_takim = mac.get("awayTeam", {})
            ev_id = ev_takim.get("id")
            dep_id = dep_takim.get("id")
            ev_adi = ev_takim.get("shortName", "?")
            dep_adi = dep_takim.get("shortName", "?")

            # Form verisi çek
            ev_maclar = api.get_team_stats(ev_id).get("matches", [])
            dep_maclar = api.get_team_stats(dep_id).get("matches", [])

            ev_formu = tahmin_motoru.son_form_analiz(ev_maclar, ev_id)
            dep_formu = tahmin_motoru.son_form_analiz(dep_maclar, dep_id)
            tahmin_sonuc, guven = tahmin_motoru.mac_tahmini(ev_formu, dep_formu)

            # Güven çubuğu
            dolu = int(guven / 10)
            bos = 10 - dolu
            cubuk = "█" * dolu + "░" * bos

            mesaj += f"⚔️ *{ev_adi}* vs *{dep_adi}*\n"
            mesaj += f"   🏠 Form: {ev_formu['galibiyet']}G {ev_formu['beraberlik']}B {ev_formu['maglubiyet']}M\n"
            mesaj += f"   ✈️ Form: {dep_formu['galibiyet']}G {dep_formu['beraberlik']}B {dep_formu['maglubiyet']}M\n"
            mesaj += f"   💡 Tahmin: {tahmin_sonuc}\n"
            mesaj += f"   📈 Güven: [{cubuk}] %{guven}\n\n"

        mesaj += "⚠️ _Tahminler istatistiksel analize dayanır._"
        await query.edit_message_text(mesaj, parse_mode="Markdown")


# ===================== GÜNLÜK BİLDİRİM =====================
async def gunluk_bildirim_gonder(context: ContextTypes.DEFAULT_TYPE):
    """Her gün belirlenen saatte tüm abonelere bildirim gönderir."""
    if not bildirim_listesi:
        return

    data = api.get_matches()
    maclar = data.get("matches", [])
    mesaj = format_mac_listesi(maclar)

    for user_id in bildirim_listesi.copy():
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🌅 *GÜNLÜK FUTBOL BÜLTENİ*\n\n{mesaj}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Bildirim gönderilemedi {user_id}: {e}")
            bildirim_listesi.discard(user_id)


# ===================== MAIN =====================
def main():
    """Botu başlat."""
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Komut işleyicileri
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bugun", bugun))
    app.add_handler(CommandHandler("puan", puan_durumu))
    app.add_handler(CommandHandler("tahmin", tahmin))
    app.add_handler(CommandHandler("bildirim", bildirim))
    app.add_handler(CommandHandler("hakkinda", hakkinda))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Günlük bildirim job'u - her gün BILDIRIM_SAATI'nde çalışır
    saat, dakika = map(int, BILDIRIM_SAATI.split(":"))
    app.job_queue.run_daily(
        gunluk_bildirim_gonder,
        time=datetime.now().replace(hour=saat, minute=dakika, second=0).time()
    )

    logger.info("⚽ Futbol Bot başlatıldı!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
