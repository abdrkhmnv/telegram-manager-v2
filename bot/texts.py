"""Panel matnlari (o'zbek tili, lotin). Barcha matnlar HTML parse_mode uchun."""

from __future__ import annotations

from bot.callbacks import Section

SECTION_TITLES: dict[Section, str] = {
    Section.SEND: "📤 Xabar yuborish",
    Section.FORWARDER: "🔁 Forwarder",
    Section.AUTOPOST: "📅 Autopost",
    Section.RANDOM_POST: "🎲 Random Autopost",
    Section.MEDIA: "🖼 Media Manager",
    Section.CHATS: "💬 Chatlar",
    Section.GROUPS: "👥 Guruhlar",
    Section.CHANNELS: "📢 Kanallar",
    Section.SEARCH: "🔎 Qidiruv",
    Section.STATS: "📊 Statistika",
    Section.SETTINGS: "⚙️ Sozlamalar",
    Section.HELP: "❓ Yordam",
}

# Bo'lim qaysi bosqichda ishga tushishi (yo'l xaritasi bo'yicha).
PLANNED_PHASE: dict[Section, int] = {
    Section.CHATS: 3,
    Section.GROUPS: 3,
    Section.CHANNELS: 3,
    Section.SEARCH: 3,
    Section.SEND: 4,
    Section.FORWARDER: 5,
    Section.AUTOPOST: 6,
    Section.RANDOM_POST: 6,
    Section.MEDIA: 7,
    Section.STATS: 7,
}

BACK = "⬅️ Orqaga"
HOME = "🏠 Bosh menyu"
STATUS_BUTTON = "ℹ️ Tizim holati"
REFRESH = "🔄 Yangilash"

MAIN_MENU = (
    "<b>Telegram Manager v2</b>\n\nBoshqaruv paneliga xush kelibsiz. Kerakli bo'limni tanlang."
)

HELP = (
    "<b>❓ Yordam</b>\n\n"
    "Bu bot sizning shaxsiy Telegram akkauntingizni boshqarish paneli. "
    "Amallarni akkauntingiz bajaradi, bot esa faqat boshqaruv vositasi.\n\n"
    "<b>Buyruqlar</b>\n"
    "/start — bosh menyu\n"
    "/help — shu yordam\n\n"
    "<b>Qoidalar</b>\n"
    "• Panelga faqat egasi kira oladi.\n"
    "• Xavfli amallar (o'chirish, ommaviy yuborish) tasdiqlashni talab qiladi.\n"
    "• Barcha vaqtlar Asia/Tashkent bo'yicha ko'rsatiladi.\n"
    "• Tizim Telegram cheklovlariga (FloodWait, anti-spam) to'liq rioya qiladi."
)

SETTINGS = (
    "<b>⚙️ Sozlamalar</b>\n\n"
    "Tizim holatini ko'rish uchun quyidagi tugmani bosing.\n"
    "Boshqa sozlamalar keyingi bosqichlarda qo'shiladi."
)

EXPIRED_CALLBACK = "Bu tugma eskirgan. Bosh menyu qayta ochildi."
BUSY = "⏳ Oldingi amal bajarilmoqda, biroz kuting."
UNKNOWN_MESSAGE = "Buyruq tushunilmadi. Bosh menyu uchun /start ni bosing."


def coming_soon(section: Section) -> str:
    title = SECTION_TITLES[section]
    phase = PLANNED_PHASE.get(section)
    when = f"{phase}-bosqichda" if phase else "keyingi bosqichlarda"
    return f"<b>{title}</b>\n\n🚧 Bu bo'lim {when} ishga tushiriladi."
