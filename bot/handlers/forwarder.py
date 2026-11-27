"""🔁 Forwarder: qoidalar ro'yxati, yangi qoida ustasi, sozlash, loglar."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import picker
from bot.callbacks import FlowCallback, NavCallback, RuleCallback, Section
from bot.content import message_html
from bot.context import Services
from bot.keyboards import button, confirm, markup, navigation_row, short
from bot.rendering import show
from bot.screens import Screen
from bot.utils import h, reply
from database.models import Chat, DeliveryStatus, ForwardMode, ForwardRule, RuleStatus
from database.repositories.rules import RuleExistsError
from services.forwarding_service import MEDIA_KINDS
from utils.time_utils import format_local
from utils.validators import InputValidationError, validate_keywords


class RuleStates(StatesGroup):
    name = State()
    mode = State()
    sources = State()
    destinations = State()
    keywords = State()
    header = State()
    footer = State()


STATUS_ICONS = {RuleStatus.ACTIVE: "🟢", RuleStatus.PAUSED: "⏸", RuleStatus.DISABLED: "⛔"}
STATUS_LABELS = {
    RuleStatus.ACTIVE: "faol",
    RuleStatus.PAUSED: "pauzada",
    RuleStatus.DISABLED: "o'chirib qo'yilgan",
}
MODE_LABELS = {ForwardMode.NATIVE: "Native forward", ForwardMode.COPY: "Copy (nusxa)"}
KIND_LABELS = {
    "text": "Matn",
    "photo": "Rasm",
    "video": "Video",
    "animation": "GIF",
    "document": "Hujjat",
    "audio": "Audio",
    "voice": "Ovozli",
    "other": "Boshqa",
}
DELIVERY_ICONS = {
    DeliveryStatus.SUCCESS: "✅",
    DeliveryStatus.FAILED: "❌",
    DeliveryStatus.SKIPPED: "⏭",
    DeliveryStatus.PENDING: "⏳",
}


async def rules_screen(svc: Services) -> Screen:
    rules = await svc.rules.list_all()
    lines = ["<b>🔁 Forwarder</b>"]
    if not rules:
        lines.append(
            "\nHali qoida yo'q. Qoida manba chatlardagi yangi xabarlarni tanlangan "
            "manzillarga avtomatik yetkazadi."
        )
    rows = [
        [
            button(
                f"{STATUS_ICONS[r.status]} {short(r.name, 28)} · {r.mode.value} · "
                f"{len(r.sources)}→{len(r.destinations)}",
                RuleCallback(act="o", id=r.id),
            )
        ]
        for r in rules
    ]
    rows.append([button("➕ Yangi qoida", FlowCallback(act="fr_new"))])
    rows.append(navigation_row())
    return Screen("\n".join(lines), markup(*rows))


def _titles(chats: Sequence[Chat], limit: int = 8) -> str:
    names = [h(short(c.title, 30)) for c in chats[:limit]]
    more = f" (+{len(chats) - limit})" if len(chats) > limit else ""
    return ", ".join(names) + more if names else "—"


async def rule_screen(svc: Services, rule_id: int) -> Screen:
    rule = await svc.rules.get(rule_id)
    if rule is None:
        return Screen("Qoida topilmadi.", markup(navigation_row(Section.FORWARDER)))
    counts = await svc.rules.counts_last_day(rule_id)
    kinds = ", ".join(KIND_LABELS[k] for k in rule.media_types) or "hammasi"
    lines = [
        f"<b>🔁 {h(rule.name)}</b>",
        "",
        f"Holat: {STATUS_ICONS[rule.status]} {STATUS_LABELS[rule.status]}",
        f"Rejim: {MODE_LABELS[rule.mode]}",
        f"Manbalar: {_titles(rule.sources)}",
        f"Manzillar: {_titles(rule.destinations)}",
        f"Kerakli so'zlar: {h(', '.join(rule.include_keywords)) or '—'}",
        f"Istisno so'zlar: {h(', '.join(rule.exclude_keywords)) or '—'}",
        f"Media turlari: {kinds}",
        f"Takrorni o'tkazib yuborish: {'ha' if rule.duplicate_detection else 'yo‘q'}",
    ]
    if rule.mode is ForwardMode.COPY:
        lines.append(f"Sarlavha: {h(short(rule.header_text or '—', 40))}")
        lines.append(f"Izoh: {h(short(rule.footer_text or '—', 40))}")
    lines.append(
        "\nOxirgi 24 soat: "
        f"✅ {counts.get(DeliveryStatus.SUCCESS, 0)} · ❌ {counts.get(DeliveryStatus.FAILED, 0)} · "
        f"⏭ {counts.get(DeliveryStatus.SKIPPED, 0)}"
    )
    pause = (
        button("⏸ Pauza", RuleCallback(act="p", id=rule.id))
        if rule.status is RuleStatus.ACTIVE
        else button("▶️ Davom ettirish", RuleCallback(act="p", id=rule.id))
    )
    disable = (
        button("✅ Yoqish", RuleCallback(act="s", id=rule.id))
        if rule.status is RuleStatus.DISABLED
        else button("⛔ O'chirib qo'yish", RuleCallback(act="s", id=rule.id))
    )
    rows = [
        [pause, disable],
        [
            button("🔤 Kalit so'zlar", RuleCallback(act="k", id=rule.id)),
            button("🎞 Media turlari", RuleCallback(act="m", id=rule.id)),
        ],
        [
            button(
                f"♻️ Takror: {'yoq' if rule.duplicate_detection else 'o‘ch'}",
                RuleCallback(act="u", id=rule.id),
            ),
            button("📋 Loglar", RuleCallback(act="l", id=rule.id)),
        ],
    ]
    if rule.mode is ForwardMode.COPY:
        rows.append(
            [
                button("📝 Sarlavha", RuleCallback(act="h", id=rule.id)),
                button("📝 Izoh", RuleCallback(act="t", id=rule.id)),
            ]
        )
    rows.append([button("🗑 O'chirish", RuleCallback(act="d", id=rule.id))])
    rows.append(navigation_row(Section.FORWARDER))
    return Screen("\n".join(lines), markup(*rows))


def media_types_screen(rule: ForwardRule) -> Screen:
    selected = set(rule.media_types or [])
    rows = [
        [
            button(
                ("✅ " if kind in selected else "▫️ ") + KIND_LABELS[kind],
                RuleCallback(act="mt", id=rule.id, arg=kind),
            )
        ]
        for kind in MEDIA_KINDS
    ]
    rows.append([button("⬅️ Orqaga", RuleCallback(act="o", id=rule.id))])
    return Screen(
        "<b>🎞 Media turlari</b>\n\nHech biri tanlanmasa — barcha turlar yo'naltiriladi.",
        markup(*rows),
    )


# ------------------------------------------------------------------ handlers
async def on_list(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await show(callback, await rules_screen(svc))


async def on_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RuleStates.name)
    await callback.answer()
    await show(
        callback,
        Screen(
            "<b>➕ Yangi qoida</b>\n\nQoida nomini yuboring (masalan: «Yangiliklar → kanalim»).",
            markup(navigation_row(Section.FORWARDER)),
        ),
    )


async def on_name(message: Message, state: FSMContext) -> None:
    name = " ".join((message.text or "").split())
    if not 1 <= len(name) <= 100:
        await message.answer("Nom 1–100 belgidan iborat bo'lishi kerak.")
        return
    await state.update_data(rule_name=name)
    await state.set_state(RuleStates.mode)
    await message.answer(
        "<b>Rejimni tanlang</b>\n\n"
        "• <b>Native forward</b> — Telegram'ning oddiy forward'i, manba ko'rsatiladi.\n"
        "• <b>Copy</b> — yangi xabar sifatida yuboriladi (forward sarlavhasisiz), "
        "formatlash va media saqlanadi, sarlavha/izoh qo'shish mumkin.\n\n"
        "Himoyalangan (nusxalash taqiqlangan) kontent hech qaysi rejimda yuborilmaydi.",
        reply_markup=markup(
            [
                button("↪️ Native forward", FlowCallback(act="fr_mode", val="native")),
                button("📄 Copy", FlowCallback(act="fr_mode", val="copy")),
            ],
            navigation_row(Section.FORWARDER),
        ),
    )


async def on_mode(
    callback: CallbackQuery, callback_data: FlowCallback, svc: Services, state: FSMContext
) -> None:
    if callback_data.val not in {m.value for m in ForwardMode}:
        await callback.answer("Noma'lum rejim")
        return
    await state.update_data(rule_mode=callback_data.val)
    await callback.answer()
    await picker.start_picker(
        callback, svc, state, target=RuleStates.sources, title="1/2 · Manba chatlarni tanlang"
    )


async def after_sources(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    data = await state.get_data()
    await state.update_data(rule_sources=list(data.get("picked", [])))
    await picker.start_picker(
        callback, svc, state, target=RuleStates.destinations, title="2/2 · Manzil chatlarni tanlang"
    )


async def after_destinations(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    data = await state.get_data()
    sources = list(data.get("rule_sources", []))
    destinations = list(data.get("picked", []))
    if set(sources) & set(destinations):
        await callback.answer("Manba va manzil bir xil chat bo'lishi mumkin emas", show_alert=True)
        return
    try:
        rule = await svc.rules.create(
            data["rule_name"], ForwardMode(data["rule_mode"]), sources, destinations
        )
    except RuleExistsError:
        await state.set_state(RuleStates.name)
        await show(
            callback,
            Screen(
                "Bu nomli qoida bor. Boshqa nom yuboring.",
                markup(navigation_row(Section.FORWARDER)),
            ),
        )
        return
    except ValueError as exc:
        await state.clear()
        await show(callback, Screen(f"❌ {h(exc)}", markup(navigation_row(Section.FORWARDER))))
        return
    await state.clear()
    await show(callback, await rule_screen(svc, rule.id))


async def on_rule(
    callback: CallbackQuery, callback_data: RuleCallback, svc: Services, state: FSMContext
) -> None:
    data = callback_data
    rule = await svc.rules.get(data.id)
    if rule is None:
        await callback.answer("Qoida topilmadi")
        await show(callback, await rules_screen(svc))
        return
    if data.act == "p":
        new = RuleStatus.PAUSED if rule.status is RuleStatus.ACTIVE else RuleStatus.ACTIVE
        await svc.rules.set_status(rule.id, new)
        await callback.answer("⏸ Pauza" if new is RuleStatus.PAUSED else "▶️ Davom etmoqda")
    elif data.act == "s":
        new = RuleStatus.ACTIVE if rule.status is RuleStatus.DISABLED else RuleStatus.DISABLED
        await svc.rules.set_status(rule.id, new)
        await callback.answer("Yoqildi" if new is RuleStatus.ACTIVE else "O'chirib qo'yildi")
    elif data.act == "u":
        await svc.rules.update(rule.id, duplicate_detection=not rule.duplicate_detection)
        await callback.answer()
    elif data.act == "m":
        await callback.answer()
        await show(callback, media_types_screen(rule))
        return
    elif data.act == "mt":
        selected = list(rule.media_types or [])
        if data.arg in selected:
            selected.remove(data.arg)
        elif data.arg in MEDIA_KINDS:
            selected.append(data.arg)
        await svc.rules.update(rule.id, media_types=selected)
        await callback.answer()
        updated = await svc.rules.get(rule.id)
        if updated is not None:
            await show(callback, media_types_screen(updated))
        return
    elif data.act in ("k", "h", "t"):
        target = {"k": RuleStates.keywords, "h": RuleStates.header, "t": RuleStates.footer}[
            data.act
        ]
        prompts = {
            "k": (
                "<b>🔤 Kalit so'zlar</b>\n\nHar bir qatorda bitta qoida:\n"
                "<code>+aksiya, chegirma</code> — shu so'zlardan biri bo'lsa yuboriladi\n"
                "<code>-reklama</code> — bu so'z bo'lsa yuborilmaydi\n"
                "<code>0</code> — barcha filtrlarni tozalash"
            ),
            "h": (
                "Xabar boshiga qo'shiladigan sarlavhani yuboring (<code>0</code> — olib tashlash)."
            ),
            "t": "Xabar oxiriga qo'shiladigan izohni yuboring (<code>0</code> — olib tashlash).",
        }
        await state.set_state(target)
        await state.update_data(rule_id=rule.id)
        await callback.answer()
        await show(
            callback,
            Screen(
                prompts[data.act],
                markup([button("❌ Bekor qilish", RuleCallback(act="o", id=rule.id))]),
            ),
        )
        return
    elif data.act == "l":
        logs = await svc.rules.recent_logs(rule.id)
        lines = [f"<b>📋 {h(rule.name)} — oxirgi yetkazishlar</b>"]
        for log in logs:
            stamp = format_local(log.created_at, svc.timezone, "%d.%m %H:%M")
            reason = f" — {h(short(log.error, 50))}" if log.error else ""
            lines.append(
                f"{DELIVERY_ICONS[log.status]} {stamp} → "
                f"<code>{log.destination_chat_telegram_id}</code>{reason}"
            )
        if not logs:
            lines.append("\nHali yetkazish bo'lmagan.")
        await callback.answer()
        await show(
            callback,
            Screen(
                "\n".join(lines), markup([button("⬅️ Orqaga", RuleCallback(act="o", id=rule.id))])
            ),
        )
        return
    elif data.act == "d":
        await callback.answer()
        await show(
            callback,
            Screen(
                f"🗑 <b>{h(rule.name)}</b> qoidasi o'chirilsinmi? Loglar statistikada qoladi.",
                markup(
                    confirm(RuleCallback(act="x", id=rule.id), RuleCallback(act="o", id=rule.id))
                ),
            ),
        )
        return
    elif data.act == "x":
        await svc.rules.delete(rule.id)
        await callback.answer("🗑 O'chirildi")
        await show(callback, await rules_screen(svc))
        return
    else:
        await state.clear()
        await callback.answer()
    await show(callback, await rule_screen(svc, rule.id))


async def on_keywords(message: Message, svc: Services, state: FSMContext) -> None:
    data = await state.get_data()
    rule_id = int(data["rule_id"])
    text = (message.text or "").strip()
    include: list[str] = []
    exclude: list[str] = []
    if text != "0":
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            target = exclude if line.startswith("-") else include
            target.extend(line.lstrip("+-").split(","))
        try:
            include = validate_keywords(include)
            exclude = validate_keywords(exclude)
        except InputValidationError as exc:
            await message.answer(str(exc))
            return
    await svc.rules.update(rule_id, include_keywords=include, exclude_keywords=exclude)
    await state.clear()
    await reply(message, await rule_screen(svc, rule_id))


async def on_header_footer(message: Message, svc: Services, state: FSMContext) -> None:
    current = await state.get_state()
    data = await state.get_data()
    rule_id = int(data["rule_id"])
    html_text = message_html(message)
    if html_text is None:
        await message.answer("Matn yuboring.")
        return
    value = None if html_text.strip() == "0" else html_text[:1000]
    field = "header_text" if current == RuleStates.header.state else "footer_text"
    await svc.rules.update(rule_id, **{field: value})
    await state.clear()
    await reply(message, await rule_screen(svc, rule_id))


def build_router() -> Router:
    picker.on_done(RuleStates.sources, after_sources)
    picker.on_done(RuleStates.destinations, after_destinations)
    router = Router(name="forwarder")
    router.callback_query.register(on_list, NavCallback.filter(F.section == Section.FORWARDER))
    router.callback_query.register(on_new, FlowCallback.filter(F.act == "fr_new"))
    router.callback_query.register(
        on_mode, StateFilter(RuleStates.mode), FlowCallback.filter(F.act == "fr_mode")
    )
    router.callback_query.register(on_rule, RuleCallback.filter())
    router.message.register(on_name, StateFilter(RuleStates.name), F.text)
    router.message.register(on_keywords, StateFilter(RuleStates.keywords), F.text)
    router.message.register(on_header_footer, StateFilter(RuleStates.header, RuleStates.footer))
    return router
