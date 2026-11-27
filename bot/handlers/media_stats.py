"""🖼 Media Manager va 📊 Statistika."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.callbacks import MediaCallback, NavCallback, Section
from bot.collect import KIND_LABELS
from bot.content import incoming_media, send_stored_preview
from bot.context import Services
from bot.keyboards import Row, button, confirm, markup, navigation_row, pager_row, short
from bot.rendering import show
from bot.screens import Screen
from bot.utils import h, human_size, when
from database.models import MediaType
from services.media_service import MediaInUseError, MediaMissingError
from services.statistics_service import Statistics, Totals
from utils.validators import InputValidationError

MEDIA_ICONS = {
    MediaType.PHOTO: "🖼",
    MediaType.VIDEO: "🎬",
    MediaType.ANIMATION: "🎞",
    MediaType.DOCUMENT: "📄",
    MediaType.AUDIO: "🎵",
    MediaType.VOICE: "🎙",
}


class MediaStates(StatesGroup):
    upload = State()


# ------------------------------------------------------------------- media
async def media_list_screen(svc: Services, page: int, note: str = "") -> Screen:
    items, page, pages = await svc.media.page(page)
    lines = ["<b>🖼 Media Manager</b>"]
    if note:
        lines.append(note)
    if not items:
        lines.append("\nHali media yo'q. ➕ Yuklash orqali qo'shing.")
    rows: list[Row] = [
        [
            button(
                f"{'⚠️' if m.is_missing else MEDIA_ICONS[m.media_type]} "
                f"{short(m.original_name or KIND_LABELS[m.media_type], 26)} · "
                f"{human_size(m.size_bytes)}",
                MediaCallback(act="o", id=m.id, page=page),
            )
        ]
        for m in items
    ]
    rows.append(pager_row(page, pages, lambda p: NavCallback(section=Section.MEDIA, page=p)))
    rows.append([button("➕ Yuklash", MediaCallback(act="u", page=page))])
    rows.append(navigation_row())
    return Screen("\n".join(lines), markup(*rows))


async def media_screen(svc: Services, media_id: int, page: int) -> Screen:
    media = await svc.media.get(media_id)
    if media is None:
        return Screen("Media topilmadi.", markup(navigation_row(Section.MEDIA, page)))
    usage = await svc.media.usage_count(media_id)
    size = f"{media.width}×{media.height}" if media.width and media.height else "—"
    lines = [
        f"<b>{MEDIA_ICONS[media.media_type]} "
        f"{h(media.original_name or KIND_LABELS[media.media_type])}</b>",
        "",
        f"Turi: {KIND_LABELS[media.media_type]} ({h(media.mime_type)})",
        f"Hajmi: {human_size(media.size_bytes)}",
        f"O'lchami: {size}",
        f"Davomiyligi: {media.duration_seconds} s" if media.duration_seconds else "Davomiyligi: —",
        f"Postlarda ishlatilgan: {usage} ta",
        f"Yuklangan: {when(media.created_at, svc.timezone)}",
        f"SHA-256: <code>{media.sha256[:16]}…</code>",
    ]
    if media.is_missing:
        lines.append("\n⚠️ Fayl diskda topilmadi.")
    return Screen(
        "\n".join(lines),
        markup(
            [
                button("👁 Ko'rish", MediaCallback(act="v", id=media_id, page=page)),
                button("🗑 O'chirish", MediaCallback(act="d", id=media_id, page=page)),
            ],
            navigation_row(Section.MEDIA, page),
        ),
    )


async def on_media_list(
    callback: CallbackQuery, callback_data: NavCallback, svc: Services, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    await show(callback, await media_list_screen(svc, callback_data.page))


async def on_media(
    callback: CallbackQuery,
    callback_data: MediaCallback,
    bot: Bot,
    svc: Services,
    state: FSMContext,
) -> None:
    data = callback_data
    if data.act == "u":
        await state.set_state(MediaStates.upload)
        await callback.answer()
        await show(
            callback,
            Screen(
                f"Fayllarni yuboring (har biri {svc.media.max_size // (1024 * 1024)} MB gacha). "
                "Rasm, video, GIF, hujjat, audio va ovozli xabarlar qabul qilinadi.",
                markup(navigation_row(Section.MEDIA)),
            ),
        )
        return
    media = await svc.media.get(data.id)
    if media is None:
        await callback.answer("Topilmadi")
        await show(callback, await media_list_screen(svc, data.page))
        return
    if data.act == "v":
        try:
            path = await svc.media.path_for(media)
        except MediaMissingError:
            await callback.answer("⚠️ Fayl diskda topilmadi", show_alert=True)
            return
        await callback.answer()
        await send_stored_preview(bot, callback.from_user.id, None, [(path, media.media_type)])
        return
    if data.act == "d":
        await callback.answer()
        await show(
            callback,
            Screen(
                "🗑 Bu media fayl o'chirilsinmi? Telegram'ga yuborilgan xabarlar o'zgarmaydi.",
                markup(
                    confirm(
                        MediaCallback(act="x", id=media.id, page=data.page),
                        MediaCallback(act="o", id=media.id, page=data.page),
                    )
                ),
            ),
        )
        return
    if data.act == "x":
        try:
            await svc.media.delete(media.id)
        except MediaInUseError:
            await callback.answer(
                "Bu media rejalashtirilgan postda ishlatilmoqda — avval postni o'chiring.",
                show_alert=True,
            )
            return
        await callback.answer("🗑 O'chirildi")
        await show(callback, await media_list_screen(svc, data.page))
        return
    await callback.answer()
    await show(callback, await media_screen(svc, media.id, data.page))


async def on_upload(message: Message, bot: Bot, svc: Services) -> None:
    found = incoming_media(message)
    if found is None:
        await message.answer("Media fayl yuboring.")
        return
    try:
        stored = await svc.media.store_from_bot(bot, found)
    except InputValidationError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    await message.answer(
        f"✅ Saqlandi: {h(stored.original_name or KIND_LABELS[stored.media_type])} "
        f"({human_size(stored.size_bytes)})",
        reply_markup=markup([button("🖼 Media ro'yxati", NavCallback(section=Section.MEDIA))]),
    )


# --------------------------------------------------------------- statistics
def _totals_lines(totals: Totals) -> list[str]:
    return [
        f"📤 Yuborilgan xabarlar: {totals.messages_sent}",
        f"↪️ Native forward: {totals.native_forwards}",
        f"📄 Copy yetkazish: {totals.copy_deliveries}",
        f"📅 Rejalashtirilgan postlar: {totals.scheduled_posts}",
        f"🎲 Random postlar: {totals.random_posts}",
        f"✅ Muvaffaqiyatli: {totals.successful} · ❌ Xato: {totals.failed}",
    ]


def stats_screen(stats: Statistics) -> Screen:
    peak = max((count for _, count in stats.daily), default=0) or 1
    bars = [
        f"<code>{day:%d.%m} {'█' * max(0, round(count / peak * 12)):<12} {count}</code>"
        for day, count in stats.daily
    ]
    lines = [
        "<b>📊 Statistika</b>",
        "",
        "<b>Jami</b>",
        *_totals_lines(stats.all_time),
        "",
        "<b>Bugun</b>",
        *_totals_lines(stats.today),
        "",
        f"<b>Oxirgi 7 kun</b> — {stats.week_total} ta muvaffaqiyatli amal",
        *bars,
        "",
        f"Vazifalar: 🟢 {stats.active_tasks} faol · ⏸ {stats.paused_tasks} pauzada",
        f"Forward qoidalari: 🟢 {stats.active_rules} faol · ⏸ {stats.paused_rules} pauzada",
    ]
    return Screen(
        "\n".join(lines),
        markup([button("🔄 Yangilash", NavCallback(section=Section.STATS))], navigation_row()),
    )


async def on_stats(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Hisoblanmoqda…")
    await show(callback, stats_screen(await svc.stats.collect()))


def build_router() -> Router:
    router = Router(name="media_stats")
    router.callback_query.register(on_media_list, NavCallback.filter(F.section == Section.MEDIA))
    router.callback_query.register(on_stats, NavCallback.filter(F.section == Section.STATS))
    router.callback_query.register(on_media, MediaCallback.filter())
    router.message.register(on_upload, StateFilter(MediaStates.upload))
    return router
