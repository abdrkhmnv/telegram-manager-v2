"""🎲 Random Autopost: belgilangan oraliqda tasodifiy vaqtda navbatdagi postni yuborish.

Tasodifiylik — faqat foydalanuvchi belgilagan [min, max] oralig'idagi vaqtni tanlash.
U Telegram anti-spam cheklovlarini chetlab o'tish vositasi emas.
"""

from __future__ import annotations

from datetime import time
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import picker
from bot.callbacks import FlowCallback, NavCallback, Section, TaskCallback
from bot.collect import upsert_status
from bot.content import incoming_media, message_html
from bot.context import Services
from bot.handlers.task_common import TASK_ICONS, TASK_LABELS
from bot.keyboards import Row, button, markup, navigation_row, short
from bot.rendering import show
from bot.screens import Screen
from bot.utils import h, when
from database.models import AutopostKind, AutopostTask, MediaType, PostStatus, TaskStatus
from services.autopost_service import DraftPost
from services.media_service import check_album
from utils.validators import (
    TELEGRAM_CAPTION_LIMIT,
    TELEGRAM_MESSAGE_LIMIT,
    InputValidationError,
    parse_hours_range,
    parse_minutes_range,
)

MAX_QUEUE_ITEMS = 100
CANCEL = FlowCallback(act="rp_cancel")


class RpStates(StatesGroup):
    pick = State()
    interval = State()
    hours = State()
    items = State()
    add_items = State()


def interval_text(task: AutopostTask) -> str:
    low = (task.min_interval_seconds or 0) // 60
    high = (task.max_interval_seconds or 0) // 60
    hours = (
        f"{task.active_from:%H:%M}–{task.active_to:%H:%M}"
        if task.active_from and task.active_to
        else "kun bo'yi"
    )
    return f"har {low}–{high} daqiqada, faol soatlar: {hours}"


async def list_screen(svc: Services) -> Screen:
    tasks = await svc.autopost.list_tasks(AutopostKind.RANDOM)
    lines = [
        "<b>🎲 Random Autopost</b>",
        "Tayyorlangan navbatdan tasodifiy post, siz belgilagan oraliqda.",
    ]
    if not tasks:
        lines.append("\nHali vazifa yo'q.")
    rows: list[Row] = [
        [
            button(
                f"{TASK_ICONS[t.status]} {short(t.name, 30)}",
                TaskCallback(act="o", id=t.id),
            )
        ]
        for t in tasks[:30]
    ]
    rows.append([button("➕ Yangi vazifa", FlowCallback(act="rp_new"))])
    rows.append(navigation_row())
    return Screen("\n".join(lines), markup(*rows))


async def task_screen(svc: Services, task_id: int) -> Screen:
    task = await svc.autopost.get(task_id)
    if task is None:
        return Screen("Vazifa topilmadi.", markup(navigation_row(Section.RANDOM_POST)))
    queue = await svc.autopost.queue(task_id)
    stats = await svc.autopost.stats(task_id)
    never = sum(1 for item in queue if item.times_posted == 0)
    lines = [
        f"<b>🎲 {h(task.name)}</b>",
        "",
        f"Holat: {TASK_ICONS[task.status]} {TASK_LABELS[task.status]}",
        f"Jadval: {interval_text(task)}",
        f"Keyingi: {when(task.next_run_at, svc.timezone)}",
        f"Oxirgi: {when(task.last_run_at, svc.timezone)}",
        f"Manzillar ({len(task.destinations)}): "
        + ", ".join(h(short(c.title, 25)) for c in task.destinations[:6]),
        f"Navbat: {len(queue)} ta post (hali yuborilmagan: {never})",
        f"Yuborilgan: ✅ {stats.get(PostStatus.SENT, 0)} · ❌ {stats.get(PostStatus.FAILED, 0)}",
    ]
    rows: list[Row] = []
    if task.status is TaskStatus.ACTIVE:
        rows.append([button("⏸ Pauza", TaskCallback(act="p", id=task.id))])
    elif task.status in (TaskStatus.PAUSED, TaskStatus.FAILED):
        rows.append([button("▶️ Davom ettirish", TaskCallback(act="p", id=task.id))])
    rows.append([button("➕ Post qo'shish", FlowCallback(act="rp_add", val=str(task.id)))])
    rows.append([button("🗑 O'chirish", TaskCallback(act="d", id=task.id))])
    rows.append(navigation_row(Section.RANDOM_POST))
    return Screen("\n".join(lines), markup(*rows))


async def on_list(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await show(callback, await list_screen(svc))


async def on_new(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await picker.start_picker(
        callback, svc, state, target=RpStates.pick, title="🎲 1/4 · Qaysi chatlarga?"
    )


async def after_pick(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    await state.set_state(RpStates.interval)
    await show(
        callback,
        Screen(
            "🎲 2/4 · Postlar orasidagi oraliqni daqiqalarda yuboring: <code>MIN-MAX</code>\n"
            "Masalan <code>60-180</code> — har 1–3 soatda. Eng kami 1 daqiqa, ko'pi 7 kun.",
            markup([button("❌ Bekor qilish", CANCEL)]),
        ),
    )


async def on_interval(message: Message, state: FSMContext) -> None:
    try:
        low, high = parse_minutes_range(message.text or "")
    except InputValidationError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    await state.update_data(rp_min=low, rp_max=high)
    await state.set_state(RpStates.hours)
    await message.answer(
        "🎲 3/4 · Faol soatlar: <code>09:00-22:00</code> yoki kun bo'yi uchun <code>0</code>.\n"
        "Yarim tundan o'tuvchi oyna ham mumkin: <code>20:00-02:00</code>.",
        reply_markup=markup([button("❌ Bekor qilish", CANCEL)]),
    )


async def on_hours(message: Message, state: FSMContext) -> None:
    try:
        start, end = parse_hours_range(message.text or "")
    except InputValidationError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    await state.update_data(
        rp_from=start.strftime("%H:%M") if start else None,
        rp_to=end.strftime("%H:%M") if end else None,
        items=[],
        status_msg_id=None,
    )
    await state.set_state(RpStates.items)
    await message.answer(
        "🎲 4/4 · Navbat uchun postlarni yuboring — har bir xabar (yoki albom) alohida post. "
        "Tugatgach ✅ Saqlash ni bosing.",
        reply_markup=markup([button("❌ Bekor qilish", CANCEL)]),
    )


async def collect_item(message: Message, bot: Bot, svc: Services, state: FSMContext) -> str | None:
    """Xabarni navbat elementiga aylantiradi; albom qismlari bitta elementga yig'iladi."""
    data = await state.get_data()
    items: list[dict[str, Any]] = list(data.get("items", []))
    if len(items) >= MAX_QUEUE_ITEMS:
        return f"Bir martada ko'pi bilan {MAX_QUEUE_ITEMS} ta post"
    found = incoming_media(message)
    html_text = message_html(message)
    if found is None and html_text is None:
        return "Matn yoki media yuboring."
    group = message.media_group_id
    current = items[-1] if items and group and items[-1].get("g") == group else None
    if current is None:
        current = {"text": None, "media": [], "g": group}
        items.append(current)
    if found is not None:
        try:
            check_album([MediaType(m["t"]) for m in current["media"]] + [found.media_type])
            stored = await svc.media.store_from_bot(bot, found)
        except InputValidationError as exc:
            if not current["media"] and not current["text"]:
                items.remove(current)
            return str(exc)
        current["media"].append({"id": stored.id, "t": found.media_type.value})
    if html_text:
        limit = TELEGRAM_CAPTION_LIMIT if current["media"] else TELEGRAM_MESSAGE_LIMIT
        if len(html_text) > limit:
            return f"Matn juda uzun (ko'pi bilan {limit} belgi)"
        current["text"] = html_text
    await state.update_data(items=items)
    return None


def _parse_time(value: str | None) -> time | None:
    return time.fromisoformat(value) if value else None


def drafts(items: list[dict[str, Any]]) -> list[DraftPost]:
    return [
        DraftPost(item.get("text"), tuple(int(m["id"]) for m in item.get("media", [])))
        for item in items
        if item.get("text") or item.get("media")
    ]


async def on_item(message: Message, bot: Bot, svc: Services, state: FSMContext) -> None:
    error = await collect_item(message, bot, svc, state)
    if error:
        await message.answer(f"⚠️ {error}")
        return
    count = len(drafts((await state.get_data()).get("items", [])))
    await upsert_status(
        message,
        bot,
        state,
        f"Navbatda: {count} ta post. Yana yuboring yoki saqlang.",
        markup(
            [
                button(f"✅ Saqlash ({count})", FlowCallback(act="rp_save")),
                button("❌ Bekor qilish", CANCEL),
            ]
        ),
    )


async def on_save(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    data = await state.get_data()
    posts = drafts(data.get("items", []))
    if not posts:
        await callback.answer("Kamida bitta post yuboring", show_alert=True)
        return
    current = await state.get_state()
    try:
        if current == RpStates.add_items.state:
            task_id = int(data["task_id"])
            await svc.autopost.add_queue_posts(task_id, posts)
        else:
            task = await svc.autopost.create_random(
                posts,
                list(data.get("picked", [])),
                min_seconds=int(data["rp_min"]),
                max_seconds=int(data["rp_max"]),
                active_from=_parse_time(data.get("rp_from")),
                active_to=_parse_time(data.get("rp_to")),
            )
            task_id = task.id
    except (InputValidationError, ValueError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await state.clear()
    await callback.answer("✅ Saqlandi")
    await show(callback, await task_screen(svc, task_id))


async def on_add(callback: CallbackQuery, callback_data: FlowCallback, state: FSMContext) -> None:
    if not callback_data.val.isdigit():
        await callback.answer()
        return
    await state.clear()
    await state.set_state(RpStates.add_items)
    await state.update_data(task_id=int(callback_data.val), items=[], status_msg_id=None)
    await callback.answer()
    await show(
        callback,
        Screen(
            "Navbatga qo'shiladigan postlarni yuboring, so'ng ✅ Saqlash.",
            markup([button("❌ Bekor qilish", TaskCallback(act="o", id=int(callback_data.val)))]),
        ),
    )


async def on_cancel(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Bekor qilindi")
    await show(callback, await list_screen(svc))


def build_router() -> Router:
    picker.on_done(RpStates.pick, after_pick)
    router = Router(name="random_post")
    router.callback_query.register(on_list, NavCallback.filter(F.section == Section.RANDOM_POST))
    router.callback_query.register(on_new, FlowCallback.filter(F.act == "rp_new"))
    router.callback_query.register(on_add, FlowCallback.filter(F.act == "rp_add"))
    router.message.register(on_interval, StateFilter(RpStates.interval), F.text)
    router.message.register(on_hours, StateFilter(RpStates.hours), F.text)
    router.message.register(on_item, StateFilter(RpStates.items, RpStates.add_items))
    router.callback_query.register(
        on_save,
        StateFilter(RpStates.items, RpStates.add_items),
        FlowCallback.filter(F.act == "rp_save"),
    )
    router.callback_query.register(on_cancel, FlowCallback.filter(F.act == "rp_cancel"))
    return router
