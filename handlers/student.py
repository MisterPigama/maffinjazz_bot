# 📄 файл: handlers/student.py

import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

import database as db
from config import ADMIN_ID
from keyboards.student_kb import student_main_menu, reg_back_kb
from utils.validators import validate_name, format_date, cooldown_remaining

logger = logging.getLogger(__name__)
router = Router()


# ─────────────────────────── FSM ───────────────────────────

class RegStates(StatesGroup):
    waiting_name = State()


# ─────────────────────────── HELPERS ───────────────────────────

async def send_balance(message_or_cq, user_record: dict) -> None:
    """Отправляет карточку баланса ученику."""
    sub = await db.get_active_subscription(user_record["id"])
    if isinstance(message_or_cq, CallbackQuery):
        send = message_or_cq.message.answer
    else:
        send = message_or_cq.answer

    if not sub:
        await send(
            "📭 У вас нет активного абонемента.\n"
            "Обратитесь к тренеру для его оформления."
        )
        return

    await send(
        f"📋 <b>Ваш абонемент</b>\n"
        f"👤 {user_record['name']}\n"
        f"📅 Действует до: <b>{format_date_str(sub['end_date'])}</b>\n"
        f"🎯 Осталось занятий: <b>{sub['lessons_left']} из {sub['total_lessons']}</b>",
        parse_mode="HTML",
    )


def format_date_str(iso: str) -> str:
    """Конвертирует ISO-дату ('YYYY-MM-DD') → 'DD.MM.YYYY'."""
    try:
        from datetime import date
        d = date.fromisoformat(iso)
        return format_date(d)
    except Exception:
        return iso


# ─────────────────────────── /start ───────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id

    # Админ не регистрируется через этот хендлер
    if user_id == ADMIN_ID:
        return

    # Проверяем, инициализирована ли БД (таблица users существует)
    try:
        existing = await db.get_user_by_telegram_id(user_id)
    except Exception:
        await message.answer(
            "⏳ Бот ещё настраивается. Попробуйте позже."
        )
        return

    if existing:
        await message.answer(
            f"👋 С возвращением, <b>{existing['name']}</b>!\n"
            "Выберите действие:",
            reply_markup=student_main_menu(),
            parse_mode="HTML",
        )
        return

    # Новый пользователь — начинаем регистрацию
    await state.set_state(RegStates.waiting_name)
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Введите ваше <b>имя и фамилию</b> для регистрации.\n"
        "<i>Допустимы буквы, пробелы, дефис и точка.</i>",
        reply_markup=reg_back_kb(),
        parse_mode="HTML",
    )


# ─────────────────────────── РЕГИСТРАЦИЯ: ВВОД ИМЕНИ ───────────────────────────

@router.message(RegStates.waiting_name)
async def process_name(message: Message, state: FSMContext) -> None:
    raw = message.text.strip() if message.text else ""

    ok, err = validate_name(raw)
    if not ok:
        await message.answer(
            f"❌ {err}\n\nВведите имя ещё раз:",
            reply_markup=reg_back_kb(),
        )
        return

    # Проверка дублей
    duplicate = await db.name_exists(raw)
    if duplicate:
        await message.answer(
            f"⚠️ Имя <b>{raw}</b> уже занято.\n"
            "Пожалуйста, добавьте фамилию или инициал, чтобы вас можно было различить.",
            reply_markup=reg_back_kb(),
            parse_mode="HTML",
        )
        return

    await db.create_user(message.from_user.id, raw.strip())
    await state.clear()

    await message.answer(
        f"✅ Вы зарегистрированы как <b>{raw.strip()}</b>!\n\n"
        "Выберите действие:",
        reply_markup=student_main_menu(),
        parse_mode="HTML",
    )


# ─────────────────────────── КНОПКА «НАЗАД» ПРИ РЕГИСТРАЦИИ ───────────────────────────

@router.callback_query(F.data == "stu:reg_back")
async def reg_back(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cq.message.edit_text(
        "Регистрация отменена.\nОтправьте /start, чтобы начать заново."
    )
    await cq.answer()


# ─────────────────────────── ПРОВЕРИТЬ БАЛАНС ───────────────────────────

@router.callback_query(F.data == "stu:check_balance")
async def check_balance(cq: CallbackQuery) -> None:
    user = await db.get_user_by_telegram_id(cq.from_user.id)
    if not user:
        await cq.answer("Сначала пройдите регистрацию (/start).", show_alert=True)
        return

    # Кулдаун 24 часа
    remaining = cooldown_remaining(user.get("last_check_time"), hours=24)
    if remaining:
        await cq.answer(
            f"⏳ Кнопка будет доступна через {remaining}",
            show_alert=True,
        )
        return

    await db.update_last_check_time(cq.from_user.id, datetime.now())

    sub = await db.get_active_subscription(user["id"])
    if not sub:
        await cq.message.answer(
            "📭 У вас нет активного абонемента.\n"
            "Обратитесь к тренеру для его оформления."
        )
    else:
        await cq.message.answer(
            f"📋 <b>Ваш абонемент</b>\n"
            f"👤 {user['name']}\n"
            f"📅 Действует до: <b>{format_date_str(sub['end_date'])}</b>\n"
            f"🎯 Осталось занятий: <b>{sub['lessons_left']} из {sub['total_lessons']}</b>",
            parse_mode="HTML",
        )
    await cq.answer()


# ─────────────────────────── ЗАПРОСИТЬ ИСПРАВЛЕНИЕ ───────────────────────────

@router.callback_query(F.data == "stu:request_edit")
async def request_edit(cq: CallbackQuery) -> None:
    user = await db.get_user_by_telegram_id(cq.from_user.id)
    if not user:
        await cq.answer("Сначала пройдите регистрацию (/start).", show_alert=True)
        return

    # Кулдаун 24 часа
    remaining = cooldown_remaining(user.get("last_edit_request_time"), hours=24)
    if remaining:
        await cq.answer(
            f"⏳ Кнопка будет доступна через {remaining}",
            show_alert=True,
        )
        return

    await db.update_last_edit_request_time(cq.from_user.id, datetime.now())

    # Уведомление админу
    username = cq.from_user.username
    mention = f"@{username}" if username else f"ID: {cq.from_user.id}"
    try:
        from aiogram import Bot
        bot: Bot = cq.bot
        await bot.send_message(
            ADMIN_ID,
            f"🔔 {mention} (<b>{user['name']}</b>) просит корректировку абонемента.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Не удалось уведомить админа о запросе исправления: %s", e)

    await cq.message.answer(
        "📨 Запрос отправлен тренеру.\n"
        "Если в течение суток нет ответа — повторите запрос."
    )
    await cq.answer()