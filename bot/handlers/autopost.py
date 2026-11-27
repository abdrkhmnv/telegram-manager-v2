"""📅 Autopost: rejalashtirilgan postlar (bir martalik, kunlik, haftalik)."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import picker
from bot.callbacks import FlowCallback, NavCallback, Section, TaskCallback
from bot.collect import collect, summary, upsert_status
from bot.context import Services
from bot.handlers import random_post
from bot.handlers.task_common import TASK_ICONS, TASK_LABELS, preview_template
from bot.keyboards import Row, button, confirm, markup, navigation_row, short
from bot.rendering import show
from bot.screens import Screen
from bot.utils import h, reply, when
from database.models import AutopostKind, AutopostTask, PostStatus, Recurrence, TaskStatus
from services.autopost_service import DraftPost
from services.message_service import plain_preview
from utils.time_utils import (
    WEEKDAY_NAMES_UZ,
    local_to_utc,
    mask_to_weekdays,
    weekdays_to_mask,
)
from utils.validators import InputValidationError, parse_local_datetime, parse_time


class ApStates(StatesGroup):
    content = State()
    pick = State()
    recurrence = State()
    weekdays = State()
    when = State()
    replace = State()


RECURRENCE_LABELS = {
    Recurrence.ONCE: "Bir martalik",
    Recurrence.DAILY: "Har kuni",
    Recurrence.WEEKLY: "Har hafta",
}
CANCEL = FlowCallback(act="ap_cancel")


def schedule_text(task: AutopostTask) -> str:
    at = task.time_of_day.strftime("%H:%M") if task.time_of_day else ""
    if task.recurrence is Recurrence.WEEKLY and task.weekdays_mask:
        days = ", ".join(WEEKDAY_NAMES_UZ[d][:3] for d in mask_to_weekdays(task.weekdays_mask))
        return f"Har hafta ({days}) {at}"
    if task.recurrence is Recurrence.DAILY:
        return f"Har kuni {at}"
    return "Bir martalik"


async def list_screen(svc: Services) -> Screen:
    tasks = await svc.autopost.list_tasks(AutopostKind.SCHEDULED)
    lines = ["<b>📅 Autopost</b>", "Rejalashtirilgan postlar (vaqtlar — Asia/Tashkent)."]
    if not tasks:
        lines.append("\nHali post yo'q.")
    rows: list[Row] = []
    for task in tasks[:30]:
        upcoming = when(task.next_run_at, svc.timezone) if task.next_run_at else "—"
        rows.append(
            [
                button(
                    f"{TASK_ICONS[task.status]} {upcoming} · {short(task.name, 26)}",
                    TaskCallback(act="o", id=task.id),
                )
            ]
        )
    rows.append([button("➕ Yangi post", FlowCallback(act="ap_new"))])
    rows.append(navigation_row())
    return Screen("\n".join(lines), markup(*rows))


async def task_screen(svc: Services, task_id: int) -> Screen:
    task = await svc.autopost.get(task_id)
    if task is None:
        return Screen("Post topilmadi.", markup(navigation_row(Section.AUTOPOST)))
    template = await svc.autopost.template(task.template_id) if task.template_id else None
    stats = await svc.autopost.stats(task_id)
    media_count = len(template.media_items) if template else 0
    lines = [
        f"<b>📅 {h(task.name)}</b>",
        "",
        f"Holat: {TASK_ICONS[task.status]} {TASK_LABELS[task.status]}",
        f"Jadval: {schedule_text(task)}",
        f"Keyingi: {when(task.next_run_at, svc.timezone)}",
        f"Oxirgi: {when(task.last_run_at, svc.timezone)}",
        f"Manzillar ({len(task.destinations)}): "
        + ", ".join(h(short(c.title, 25)) for c in task.destinations[:6]),
        f"Kontent: {h(short(plain_preview(template.text if template else None), 80))}"
        + (f" + {media_count} ta media" if media_count else ""),
        f"Yuborilgan: ✅ {stats.get(PostStatus.SENT, 0)} · ❌ {stats.get(PostStatus.FAILED, 0)}",
    ]
    if task.consecutive_failures:
        lines.append(f"⚠️ Ketma-ket xatolar: {task.consecutive_failures}")
    rows: list[Row] = []
    if task.status is TaskStatus.ACTIVE:
        rows.append([button("⏸ Pauza", TaskCallback(act="p", id=task.id))])
    elif task.status in (TaskStatus.PAUSED, TaskStatus.FAILED):
        rows.append([button("▶️ Davom ettirish", TaskCallback(act="p", id=task.id))])
    rows.append(
        [
            button("👁 Ko'rish", TaskCallback(act="v", id=task.id)),
            button("✏️ Kontentni almashtirish", TaskCallback(act="e", id=task.id)),
        ]
    )
    if task.status in (TaskStatus.ACTIVE, TaskStatus.PAUSED):
        rows.append([button("🚫 Bekor qilish", TaskCallback(act="c", id=task.id))])
    rows.append([button("🗑 O'chirish", TaskCallback(act="d", id=task.id))])
    rows.append(navigation_row(Section.AUTOPOST))
    return Screen("\n".join(lines), markup(*rows))


# ------------------------------------------------------------- list & detail
async def on_list(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await show(callback, await list_screen(svc))


async def on_task(
    callback: CallbackQuery,
    callback_data: TaskCallback,
    bot: Bot,
    svc: Services,
    state: FSMContext,
) -> None:
    data = callback_data
    task = await svc.autopost.get(data.id)
    if task is None:
        await callback.answer("Topilmadi")
        await show(callback, Screen("Vazifa topilmadi.", markup(navigation_row())))
        return
    back = Section.AUTOPOST if task.kind is AutopostKind.SCHEDULED else Section.RANDOM_POST
    if data.act == "p":
        if task.status is TaskStatus.ACTIVE:
            await svc.autopost.pause(task.id)
            await callback.answer("⏸ Pauza")
        else:
            await svc.autopost.resume(task.id)
            await callback.answer("▶️ Davom etmoqda")
    elif data.act == "v" and task.template_id:
        await callback.answer()
        await preview_template(bot, callback.from_user.id, svc, task.template_id)
        return
    elif data.act == "e":
        await state.set_state(ApStates.replace)
        await state.update_data(task_id=task.id, text=None, media=[], status_msg_id=None)
        await callback.answer()
        await show(
            callback,
            Screen(
                "Yangi kontentni yuboring (matn va/yoki media), so'ng 💾 Saqlash.",
                markup([button("❌ Bekor qilish", TaskCallback(act="o", id=task.id))]),
            ),
        )
        return
    elif data.act in ("c", "d"):
        verb = (
            "bekor qilinsinmi (keyingi yuborishlar to'xtaydi)"
            if data.act == "c"
            else "o'chirilsinmi"
        )
        await callback.answer()
        await show(
            callback,
            Screen(
                f"<b>{h(task.name)}</b> {verb}?",
                markup(
                    confirm(
                        TaskCallback(act="x", id=task.id, arg=1 if data.act == "d" else 0),
                        TaskCallback(act="o", id=task.id),
                    )
                ),
            ),
        )
        return
    elif data.act == "x":
        if data.arg == 1:
            await svc.autopost.delete(task.id)
            await callback.answer("🗑 O'chirildi")
            screen = (
                await list_screen(svc)
                if back is Section.AUTOPOST
                else await random_post.list_screen(svc)
            )
            await show(callback, screen)
            return
        await svc.autopost.cancel(task.id)
        await callback.answer("🚫 Bekor qilindi")
    else:
        await state.clear()
        await callback.answer()
    if task.kind is AutopostKind.RANDOM:
        await show(callback, await random_post.task_screen(svc, task.id))
    else:
        await show(callback, await task_screen(svc, task.id))


async def on_replace_content(message: Message, bot: Bot, svc: Services, state: FSMContext) -> None:
    error = await collect(message, bot, svc, state)
    if error:
        await message.answer(f"⚠️ {error}")
        return
    await upsert_status(
        message,
        bot,
        state,
        f"Qabul qilindi: {await summary(state)}.",
        markup(
            [
                button("💾 Saqlash", FlowCallback(act="ap_save_content")),
                button("❌ Bekor qilish", CANCEL),
            ]
        ),
    )


async def on_save_content(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    data = await state.get_data()
    post = DraftPost(data.get("text"), tuple(int(m["id"]) for m in data.get("media", [])))
    if not post.text and not post.media_ids:
        await callback.answer("Avval kontent yuboring", show_alert=True)
        return
    task_id = int(data["task_id"])
    await state.clear()
    try:
        await svc.autopost.replace_content(task_id, post)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("💾 Saqlandi")
    await show(callback, await task_screen(svc, task_id))


# ------------------------------------------------------------- creation wizard
async def on_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ApStates.content)
    await state.update_data(text=None, media=[], status_msg_id=None)
    await callback.answer()
    await show(
        callback,
        Screen(
            "<b>➕ Yangi post</b>\n\n1/3 · Post mazmunini yuboring: matn, rasm, video, hujjat, "
            "audio yoki albom. Formatlash saqlanadi.",
            markup([button("❌ Bekor qilish", CANCEL)]),
        ),
    )


async def on_content(message: Message, bot: Bot, svc: Services, state: FSMContext) -> None:
    error = await collect(message, bot, svc, state)
    if error:
        await message.answer(f"⚠️ {error}")
        return
    await upsert_status(
        message,
        bot,
        state,
        f"Qabul qilindi: {await summary(state)}.",
        markup(
            [
                button("➡️ Davom etish", FlowCallback(act="ap_next")),
                button("❌ Bekor qilish", CANCEL),
            ]
        ),
    )


async def on_content_done(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("text") and not data.get("media"):
        await callback.answer("Avval post mazmunini yuboring", show_alert=True)
        return
    await callback.answer()
    await picker.start_picker(
        callback, svc, state, target=ApStates.pick, title="2/3 · Qaysi chatlarga?"
    )


async def after_pick(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    await state.set_state(ApStates.recurrence)
    await show(
        callback,
        Screen(
            "3/3 · Qachon yuborilsin?",
            markup(
                [
                    button("1️⃣ Bir marta", FlowCallback(act="ap_rec", val="once")),
                    button("🔁 Har kuni", FlowCallback(act="ap_rec", val="daily")),
                    button("📆 Har hafta", FlowCallback(act="ap_rec", val="weekly")),
                ],
                [button("❌ Bekor qilish", CANCEL)],
            ),
        ),
    )


def weekdays_screen(selected: set[int]) -> Screen:
    rows = [
        [
            button(
                ("✅ " if day in selected else "▫️ ") + name,
                FlowCallback(act="ap_wd", val=str(day)),
            )
        ]
        for day, name in enumerate(WEEKDAY_NAMES_UZ)
    ]
    rows.append(
        [button("➡️ Davom etish", FlowCallback(act="ap_wd_done")), button("❌ Bekor qilish", CANCEL)]
    )
    return Screen("Hafta kunlarini tanlang:", markup(*rows))


async def on_recurrence(
    callback: CallbackQuery, callback_data: FlowCallback, state: FSMContext
) -> None:
    if callback_data.val not in {r.value for r in Recurrence}:
        await callback.answer("Noma'lum tanlov")
        return
    await state.update_data(recurrence=callback_data.val, weekdays=[])
    await callback.answer()
    if callback_data.val == Recurrence.WEEKLY.value:
        await state.set_state(ApStates.weekdays)
        await show(callback, weekdays_screen(set()))
        return
    await ask_when(callback, state, Recurrence(callback_data.val))


async def ask_when(callback: CallbackQuery, state: FSMContext, recurrence: Recurrence) -> None:
    await state.set_state(ApStates.when)
    prompt = (
        "Sana va vaqtni yuboring: <code>KK.OO.YYYY SS:DD</code> (masalan 28.11.2026 09:30)"
        if recurrence is Recurrence.ONCE
        else "Vaqtni yuboring: <code>SS:DD</code> (masalan 09:30)"
    )
    await show(
        callback,
        Screen(
            prompt + "\nVaqt zonasi: Asia/Tashkent.", markup([button("❌ Bekor qilish", CANCEL)])
        ),
    )


async def on_weekday(
    callback: CallbackQuery, callback_data: FlowCallback, state: FSMContext
) -> None:
    data = await state.get_data()
    selected = set(int(d) for d in data.get("weekdays", []))
    if not callback_data.val.isdigit() or not 0 <= int(callback_data.val) <= 6:
        await callback.answer()
        return
    day = int(callback_data.val)
    selected ^= {day}
    await state.update_data(weekdays=sorted(selected))
    await callback.answer()
    await show(callback, weekdays_screen(selected))


async def on_weekdays_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("weekdays"):
        await callback.answer("Kamida bitta kunni tanlang", show_alert=True)
        return
    await callback.answer()
    await ask_when(callback, state, Recurrence.WEEKLY)


async def on_when(message: Message, svc: Services, state: FSMContext) -> None:
    data = await state.get_data()
    recurrence = Recurrence(data["recurrence"])
    text = message.text or ""
    try:
        if recurrence is Recurrence.ONCE:
            local = parse_local_datetime(text)
            run_at = local_to_utc(local, svc.timezone)
            at = local.time()
        else:
            run_at = None
            at = parse_time(text)
        mask = weekdays_to_mask(data["weekdays"]) if recurrence is Recurrence.WEEKLY else None
        task = await svc.autopost.create_scheduled(
            DraftPost(data.get("text"), tuple(int(m["id"]) for m in data.get("media", []))),
            list(data.get("picked", [])),
            recurrence=recurrence,
            at=at,
            run_at=run_at,
            weekdays_mask=mask,
        )
    except (InputValidationError, ValueError) as exc:
        await message.answer(f"⚠️ {exc}")
        return
    await state.clear()
    await message.answer("✅ Post rejalashtirildi.")
    await reply(message, await task_screen(svc, task.id))


async def on_cancel(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Bekor qilindi")
    await show(callback, await list_screen(svc))


def build_router() -> Router:
    picker.on_done(ApStates.pick, after_pick)
    router = Router(name="autopost")
    router.callback_query.register(on_list, NavCallback.filter(F.section == Section.AUTOPOST))
    router.callback_query.register(on_new, FlowCallback.filter(F.act == "ap_new"))
    router.callback_query.register(on_task, TaskCallback.filter())
    router.message.register(on_content, StateFilter(ApStates.content))
    router.message.register(on_replace_content, StateFilter(ApStates.replace))
    router.message.register(on_when, StateFilter(ApStates.when), F.text)
    router.callback_query.register(
        on_content_done, StateFilter(ApStates.content), FlowCallback.filter(F.act == "ap_next")
    )
    router.callback_query.register(
        on_save_content,
        StateFilter(ApStates.replace),
        FlowCallback.filter(F.act == "ap_save_content"),
    )
    router.callback_query.register(
        on_recurrence, StateFilter(ApStates.recurrence), FlowCallback.filter(F.act == "ap_rec")
    )
    router.callback_query.register(
        on_weekday, StateFilter(ApStates.weekdays), FlowCallback.filter(F.act == "ap_wd")
    )
    router.callback_query.register(
        on_weekdays_done, StateFilter(ApStates.weekdays), FlowCallback.filter(F.act == "ap_wd_done")
    )
    router.callback_query.register(on_cancel, FlowCallback.filter(F.act == "ap_cancel"))
    return router
