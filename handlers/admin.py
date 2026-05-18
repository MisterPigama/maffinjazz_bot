# 📄 файл: handlers/admin.py

import logging
from datetime import date, datetime

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from dateutil.relativedelta import relativedelta

import database as db
from config import ADMIN_ID
from keyboards.admin_kb import (
    admin_main_menu,
    students_list_kb,
    subscription_edit_kb,
    lessons_choice_kb,
    lesson_spent_kb,
    attend_kb,
    back_to_main_kb,
)
from utils.validators import (
    format_date,
    parse_date,
    parse_date_range,
)

logger = logging.getLogger(__name__)
router = Router()


# ─────────────────────────── FSM ───────────────────────────

class AdminStates(StatesGroup):
    # Новый абонемент
    choosing_student_new   = State()
    entering_start_date    = State()
    confirming_spent       = State()

    # Редактирование
    choosing_student_edit  = State()
    viewing_subscription   = State()
    entering_date_range    = State()

    # Отметка посещения
    marking_attendance     = State()


# ─────────────────────────── HELPERS ───────────────────────────

def _iso_to_display(iso: str) -> str:
    try:
        return format_date(date.fromisoformat(iso))
    except Exception:
        return iso


def _sub_card(user: dict, sub: dict) -> str:
    today = date.today()
    end = date.fromisoformat(sub["end_date"])
    days_left = (end - today).days
    warn_date = "⚠️ " if days_left <= 7 else ""
    warn_less = "⚠️ " if sub["lessons_left"] <= 2 else ""

    return (
        f"👤 <b>{user['name']}</b>\n"
        f"📅 Начало: {_iso_to_display(sub['start_date'])}\n"
        f"{warn_date}📅 Конец: <b>{_iso_to_display(sub['end_date'])}</b>"
        + (f" (через {days_left} дн.)" if days_left >= 0 else " (просрочен)") + "\n"
        f"{warn_less}🎯 Осталось: <b>{sub['lessons_left']} из {sub['total_lessons']}</b>\n"
        f"🆔 Абонемент #{sub['id']}"
    )


async def _notify_student(
    bot: Bot,
    telegram_id: int,
    text: str,
    admin_id: int,
) -> None:
    """Отправляет уведомление ученику. При ошибке логирует и сообщает админу."""
    try:
        await bot.send_message(telegram_id, text, parse_mode="HTML")
    except TelegramBadRequest as e:
        logger.warning("TelegramBadRequest при уведомлении %s: %s", telegram_id, e)
        await bot.send_message(
            admin_id,
            f"⚠️ Не удалось уведомить пользователя (ID: <code>{telegram_id}</code>).\n"
            f"Вероятно, он заблокировал бота.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Ошибка уведомления %s: %s", telegram_id, e)


# ─────────────────────────── /start (АДМИН) ───────────────────────────

@router.message(CommandStart(), F.from_user.id == ADMIN_ID)
async def admin_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await db.init_db()
    await db.expire_overdue_subscriptions()
    await message.answer(
        "👋 Добро пожаловать в панель администратора!",
        reply_markup=admin_main_menu(),
    )


# ─────────────────────────── ГЛАВНОЕ МЕНЮ ───────────────────────────

@router.callback_query(F.data == "adm:back_main", F.from_user.id == ADMIN_ID)
async def back_to_main(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cq.message.edit_text(
        "🏠 Главное меню администратора:",
        reply_markup=admin_main_menu(),
    )
    await cq.answer()


# ─────────────────────────── СПИСОК УЧЕНИКОВ (просмотр) ───────────────────────────

@router.callback_query(F.data == "adm:students", F.from_user.id == ADMIN_ID)
async def show_students(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    students = await db.get_all_students()
    # Исключаем самого админа из списка учеников
    students = [s for s in students if s["telegram_id"] != ADMIN_ID]
    if not students:
        await cq.message.edit_text(
            "👥 Учеников пока нет.",
            reply_markup=back_to_main_kb(),
        )
        await cq.answer()
        return
    await cq.message.edit_text(
        "👥 Список учеников:",
        reply_markup=students_list_kb(students, action="view_sub"),
    )
    await cq.answer()


# ─────────────────────────── НОВЫЙ АБОНЕМЕНТ: ВЫБОР УЧЕНИКА ───────────────────────────

@router.callback_query(F.data == "adm:new_sub", F.from_user.id == ADMIN_ID)
async def new_sub_choose_student(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    students = await db.get_all_students()
    students = [s for s in students if s["telegram_id"] != ADMIN_ID]
    if not students:
        await cq.message.edit_text(
            "👥 Учеников пока нет. Сначала ученики должны запустить бота.",
            reply_markup=back_to_main_kb(),
        )
        await cq.answer()
        return
    await state.set_state(AdminStates.choosing_student_new)
    await cq.message.edit_text(
        "➕ Выберите ученика для нового абонемента:",
        reply_markup=students_list_kb(students, action="new_sub"),
    )
    await cq.answer()


@router.callback_query(
    AdminStates.choosing_student_new,
    F.data.startswith("act:new_sub:u"),
    F.from_user.id == ADMIN_ID,
)
async def new_sub_student_selected(cq: CallbackQuery, state: FSMContext) -> None:
    user_id = int(cq.data.split(":")[2][1:])  # u{id} → int
    user = await db.get_user_by_id(user_id)
    if not user:
        await cq.answer("Ученик не найден.", show_alert=True)
        return

    # Проверяем, нет ли уже активного абонемента
    existing_sub = await db.get_active_subscription(user_id)
    if existing_sub:
        await cq.message.edit_text(
            f"⚠️ У <b>{user['name']}</b> уже есть активный абонемент.\n\n"
            + _sub_card(user, existing_sub),
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
        await cq.answer()
        return

    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminStates.entering_start_date)
    await cq.message.edit_text(
        f"📅 Введите дату начала абонемента для <b>{user['name']}</b>\n"
        f"Формат: ДД.ММ.ГГГГ",
        reply_markup=back_to_main_kb(),
        parse_mode="HTML",
    )
    await cq.answer()


@router.message(AdminStates.entering_start_date, F.from_user.id == ADMIN_ID)
async def new_sub_enter_date(message: Message, state: FSMContext) -> None:
    raw = message.text.strip() if message.text else ""
    start = parse_date(raw)
    if not start:
        await message.answer(
            "❌ Неверный формат даты. Ожидается ДД.ММ.ГГГГ\nНапример: 01.06.2025",
            reply_markup=back_to_main_kb(),
        )
        return

    data = await state.get_data()
    user_id = data["target_user_id"]
    user = await db.get_user_by_id(user_id)

    await state.update_data(start_date=start.isoformat())

    today = date.today()
    if start <= today:
        # Спрашиваем, было ли потрачено занятие
        await state.set_state(AdminStates.confirming_spent)
        await message.answer(
            f"📅 Дата начала: <b>{format_date(start)}</b>\n\n"
            f"Эта дата уже наступила. Было ли сегодня проведено занятие?",
            reply_markup=lesson_spent_kb(user_id),
            parse_mode="HTML",
        )
    else:
        # Дата в будущем — создаём сразу с 8 занятиями
        await _create_subscription(
            bot=message.bot,
            admin_id=message.from_user.id,
            user=user,
            start=start,
            lessons_left=8,
            state=state,
            reply_target=message,
        )


# ─────────────────────────── ВОПРОС «ПОТРАЧЕНО ЗАНЯТИЕ?» ───────────────────────────

@router.callback_query(
    AdminStates.confirming_spent,
    F.data.startswith("act:spent_"),
    F.from_user.id == ADMIN_ID,
)
async def confirm_spent(cq: CallbackQuery, state: FSMContext) -> None:
    parts = cq.data.split(":")   # act : spent_yes/spent_no : u{id}
    action = parts[1]            # spent_yes | spent_no
    user_id = int(parts[2][1:])  # u{id} → int

    data = await state.get_data()
    start = date.fromisoformat(data["start_date"])
    user = await db.get_user_by_id(user_id)

    lessons_left = 7 if action == "spent_yes" else 8

    await _create_subscription(
        bot=cq.bot,
        admin_id=cq.from_user.id,
        user=user,
        start=start,
        lessons_left=lessons_left,
        state=state,
        reply_target=cq,
    )
    await cq.answer()


async def _create_subscription(
    bot: Bot,
    admin_id: int,
    user: dict,
    start: date,
    lessons_left: int,
    state: FSMContext,
    reply_target,
) -> None:
    end = start + relativedelta(months=1)
    sub_id = await db.create_subscription(
        user_id=user["id"],
        start_date=start,
        end_date=end,
        lessons_left=lessons_left,
        total_lessons=8,
    )
    sub = await db.get_subscription_by_id(sub_id)
    await state.clear()

    card = (
        f"✅ <b>Абонемент создан!</b>\n\n"
        + _sub_card(user, sub)
    )

    # Ответ админу
    if isinstance(reply_target, CallbackQuery):
        await reply_target.message.edit_text(
            card,
            reply_markup=admin_main_menu(),
            parse_mode="HTML",
        )
    else:
        await reply_target.answer(
            card,
            reply_markup=admin_main_menu(),
            parse_mode="HTML",
        )

    # Уведомление ученику
    await _notify_student(
        bot=bot,
        telegram_id=user["telegram_id"],
        text=(
            f"✅ <b>Абонемент активирован!</b>\n"
            f"🎯 Осталось: <b>{lessons_left} из 8</b>\n"
            f"📅 Действует до: <b>{format_date(end)}</b>"
        ),
        admin_id=admin_id,
    )


# ─────────────────────────── ВСЕ АБОНЕМЕНТЫ ───────────────────────────

@router.callback_query(F.data == "adm:all_subs", F.from_user.id == ADMIN_ID)
async def all_subs(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await db.expire_overdue_subscriptions()
    subs = await db.get_all_active_subscriptions_with_users()

    if not subs:
        await cq.message.edit_text(
            "📋 Активных абонементов нет.",
            reply_markup=back_to_main_kb(),
        )
        await cq.answer()
        return

    today = date.today()

    def _priority(s: dict) -> int:
        end = date.fromisoformat(s["end_date"])
        days = (end - today).days
        if days <= 7 or s["lessons_left"] <= 2:
            return 0
        return 1

    subs_sorted = sorted(subs, key=lambda s: (_priority(s), s["end_date"]))

    lines = []
    for s in subs_sorted:
        end = date.fromisoformat(s["end_date"])
        days_left = (end - today).days
        warn = "⚠️ " if days_left <= 7 or s["lessons_left"] <= 2 else ""
        lines.append(
            f"{warn}<b>{s['name']}</b> — "
            f"{s['lessons_left']}/{s['total_lessons']} зан., "
            f"до {_iso_to_display(s['end_date'])}"
        )

    text = "📋 <b>Активные абонементы:</b>\n\n" + "\n".join(lines)
    await cq.message.edit_text(
        text,
        reply_markup=back_to_main_kb(),
        parse_mode="HTML",
    )
    await cq.answer()


# ─────────────────────────── РЕДАКТИРОВАНИЕ: ВЫБОР УЧЕНИКА ───────────────────────────

@router.callback_query(
    F.data.in_({"adm:students_edit", "adm:edit_sub"}),
    F.from_user.id == ADMIN_ID,
)
async def edit_sub_choose_student(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    students = await db.get_all_students()
    students = [s for s in students if s["telegram_id"] != ADMIN_ID]
    if not students:
        await cq.message.edit_text(
            "👥 Учеников нет.",
            reply_markup=back_to_main_kb(),
        )
        await cq.answer()
        return
    await state.set_state(AdminStates.choosing_student_edit)
    await cq.message.edit_text(
        "✏️ Выберите ученика для редактирования:",
        reply_markup=students_list_kb(students, action="edit_sub"),
    )
    await cq.answer()


@router.callback_query(
    AdminStates.choosing_student_edit,
    F.data.startswith("act:edit_sub:u"),
    F.from_user.id == ADMIN_ID,
)
async def edit_sub_student_selected(cq: CallbackQuery, state: FSMContext) -> None:
    user_id = int(cq.data.split(":")[2][1:])
    user = await db.get_user_by_id(user_id)
    if not user:
        await cq.answer("Ученик не найден.", show_alert=True)
        return

    sub = await db.get_active_subscription(user_id)
    if not sub:
        await cq.message.edit_text(
            f"📭 У <b>{user['name']}</b> нет активного абонемента.",
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
        await cq.answer()
        return

    await state.set_state(AdminStates.viewing_subscription)
    await state.update_data(target_user_id=user_id, sub_id=sub["id"])
    await cq.message.edit_text(
        _sub_card(user, sub),
        reply_markup=subscription_edit_kb(sub["id"]),
        parse_mode="HTML",
    )
    await cq.answer()


# ─────────────────────────── РЕДАКТИРОВАНИЕ: НАЗАД К КАРТОЧКЕ ───────────────────────────

@router.callback_query(
    F.data.startswith("act:edit_sub:s"),
    F.from_user.id == ADMIN_ID,
)
async def back_to_sub_card(cq: CallbackQuery, state: FSMContext) -> None:
    sub_id = int(cq.data.split(":")[2][1:])
    sub = await db.get_subscription_by_id(sub_id)
    if not sub:
        await cq.answer("Абонемент не найден.", show_alert=True)
        return
    user = await db.get_user_by_id(sub["user_id"])
    await state.set_state(AdminStates.viewing_subscription)
    await state.update_data(target_user_id=sub["user_id"], sub_id=sub_id)
    await cq.message.edit_text(
        _sub_card(user, sub),
        reply_markup=subscription_edit_kb(sub_id),
        parse_mode="HTML",
    )
    await cq.answer()


# ─────────────────────────── РЕДАКТИРОВАНИЕ: ИЗМЕНИТЬ ДАТЫ ───────────────────────────

@router.callback_query(
    F.data.startswith("act:edit_dates:s"),
    F.from_user.id == ADMIN_ID,
)
async def edit_dates_prompt(cq: CallbackQuery, state: FSMContext) -> None:
    sub_id = int(cq.data.split(":")[2][1:])
    await state.set_state(AdminStates.entering_date_range)
    await state.update_data(sub_id=sub_id)
    await cq.message.edit_text(
        "📅 Введите новый период абонемента в формате:\n"
        "<b>ДД.ММ.ГГГГ - ДД.ММ.ГГГГ</b>\n\n"
        "Например: 01.06.2025 - 01.07.2025",
        reply_markup=back_to_main_kb(),
        parse_mode="HTML",
    )
    await cq.answer()


@router.message(AdminStates.entering_date_range, F.from_user.id == ADMIN_ID)
async def edit_dates_process(message: Message, state: FSMContext) -> None:
    raw = message.text.strip() if message.text else ""
    start, end, err = parse_date_range(raw)
    if err:
        await message.answer(
            f"❌ {err}",
            reply_markup=back_to_main_kb(),
        )
        return

    data = await state.get_data()
    sub_id = data["sub_id"]
    await db.update_subscription_dates(sub_id, start, end)

    sub = await db.get_subscription_by_id(sub_id)
    user = await db.get_user_by_id(sub["user_id"])
    await state.set_state(AdminStates.viewing_subscription)
    await state.update_data(target_user_id=sub["user_id"], sub_id=sub_id)

    await message.answer(
        f"✅ Даты обновлены!\n\n" + _sub_card(user, sub),
        reply_markup=subscription_edit_kb(sub_id),
        parse_mode="HTML",
    )

    # Уведомление ученику
    await _notify_student(
        bot=message.bot,
        telegram_id=user["telegram_id"],
        text=(
            f"✏️ <b>Абонемент обновлён.</b>\n"
            f"📅 Новый период: <b>{format_date(start)} — {format_date(end)}</b>\n"
            f"🎯 Осталось занятий: <b>{sub['lessons_left']} из {sub['total_lessons']}</b>"
        ),
        admin_id=message.from_user.id,
    )


# ─────────────────────────── РЕДАКТИРОВАНИЕ: ИЗМЕНИТЬ КОЛ-ВО ЗАНЯТИЙ ───────────────────────────

@router.callback_query(
    F.data.startswith("act:edit_lessons:s"),
    F.from_user.id == ADMIN_ID,
)
async def edit_lessons_prompt(cq: CallbackQuery, state: FSMContext) -> None:
    sub_id = int(cq.data.split(":")[2][1:])
    await cq.message.edit_text(
        "🔢 Выберите новое количество оставшихся занятий:",
        reply_markup=lessons_choice_kb(sub_id),
    )
    await cq.answer()


@router.callback_query(
    F.data.startswith("act:set_lessons:s"),
    F.from_user.id == ADMIN_ID,
)
async def set_lessons(cq: CallbackQuery, state: FSMContext) -> None:
    # act:set_lessons:s{sub_id}:{n}
    parts = cq.data.split(":")
    sub_id = int(parts[2][1:])
    lessons = int(parts[3])

    await db.update_subscription_lessons(sub_id, lessons)
    sub = await db.get_subscription_by_id(sub_id)
    user = await db.get_user_by_id(sub["user_id"])

    await state.set_state(AdminStates.viewing_subscription)
    await state.update_data(target_user_id=sub["user_id"], sub_id=sub_id)

    await cq.message.edit_text(
        f"✅ Занятия обновлены!\n\n" + _sub_card(user, sub),
        reply_markup=subscription_edit_kb(sub_id),
        parse_mode="HTML",
    )

    end = date.fromisoformat(sub["end_date"])
    await _notify_student(
        bot=cq.bot,
        telegram_id=user["telegram_id"],
        text=(
            f"✏️ <b>Абонемент обновлён.</b>\n"
            f"🎯 Осталось занятий: <b>{lessons} из {sub['total_lessons']}</b>\n"
            f"📅 Действует до: <b>{format_date(end)}</b>"
        ),
        admin_id=cq.from_user.id,
    )
    await cq.answer()


# ─────────────────────────── ОТМЕТКА ПОСЕЩЕНИЯ ───────────────────────────

@router.callback_query(F.data == "adm:attend", F.from_user.id == ADMIN_ID)
async def attend_start(cq: CallbackQuery, state: FSMContext) -> None:
    await db.expire_overdue_subscriptions()
    subs = await db.get_attendable_subscriptions()
    if not subs:
        await cq.message.edit_text(
            "📭 Нет учеников с активными абонементами.",
            reply_markup=back_to_main_kb(),
        )
        await cq.answer()
        return

    await state.set_state(AdminStates.marking_attendance)
    await state.update_data(selected=[], subs=[
        {k: v for k, v in s.items()} for s in subs
    ])
    await cq.message.edit_text(
        "✅ Отметьте присутствующих учеников:",
        reply_markup=attend_kb(subs, selected=set()),
    )
    await cq.answer()


@router.callback_query(
    AdminStates.marking_attendance,
    F.data.startswith("act:toggle_attend:s"),
    F.from_user.id == ADMIN_ID,
)
async def toggle_attend(cq: CallbackQuery, state: FSMContext) -> None:
    sub_id = int(cq.data.split(":")[2][1:])
    data = await state.get_data()
    selected: list = data.get("selected", [])
    subs: list = data.get("subs", [])

    if sub_id in selected:
        selected.remove(sub_id)
    else:
        selected.append(sub_id)

    await state.update_data(selected=selected)
    await cq.message.edit_reply_markup(
        reply_markup=attend_kb(subs, selected=set(selected))
    )
    await cq.answer()


@router.callback_query(
    F.data == "adm:save_attend",
    F.from_user.id == ADMIN_ID,
)
async def save_attend(cq: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected: list = data.get("selected", [])

    if not selected:
        await cq.answer("⚠️ Никто не выбран.", show_alert=True)
        return

    finished = 0
    for sub_id in selected:
        new_left = await db.mark_lesson(sub_id, admin_id=cq.from_user.id)
        sub = await db.get_subscription_by_id(sub_id)
        user = await db.get_user_by_id(sub["user_id"])
        end = date.fromisoformat(sub["end_date"])

        if new_left == 0:
            finished += 1
            text = (
                f"📅 Занятие отмечено.\n"
                f"🏁 <b>Абонемент завершён.</b> Осталось: 0 из {sub['total_lessons']}.\n"
                f"📅 Действовал до: <b>{format_date(end)}</b>"
            )
        else:
            text = (
                f"📅 Занятие отмечено.\n"
                f"🎯 Осталось: <b>{new_left} из {sub['total_lessons']}</b>\n"
                f"📅 Действует до: <b>{format_date(end)}</b>"
            )

        await _notify_student(
            bot=cq.bot,
            telegram_id=user["telegram_id"],
            text=text,
            admin_id=cq.from_user.id,
        )

    await state.clear()
    await cq.message.edit_text(
        f"✅ <b>Отмечено учеников: {len(selected)}</b>\n"
        f"🏁 Абонементы завершены: {finished}",
        reply_markup=admin_main_menu(),
        parse_mode="HTML",
    )
    await cq.answer()


# ─────────────────────────── ПРОСМОТР АБОНЕМЕНТА УЧЕНИКА ───────────────────────────

@router.callback_query(
    F.data.startswith("act:view_sub:u"),
    F.from_user.id == ADMIN_ID,
)
async def view_student_sub(cq: CallbackQuery, state: FSMContext) -> None:
    user_id = int(cq.data.split(":")[2][1:])
    user = await db.get_user_by_id(user_id)
    if not user:
        await cq.answer("Ученик не найден.", show_alert=True)
        return

    sub = await db.get_active_subscription(user_id)
    if not sub:
        await cq.message.edit_text(
            f"📭 У <b>{user['name']}</b> нет активного абонемента.",
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
        await cq.answer()
        return

    await cq.message.edit_text(
        _sub_card(user, sub),
        reply_markup=subscription_edit_kb(sub["id"]),
        parse_mode="HTML",
    )
    await cq.answer()