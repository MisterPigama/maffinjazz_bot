# 📄 файл: keyboards/student_kb.py

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ─────────────────────────── ГЛАВНОЕ МЕНЮ УЧЕНИКА ───────────────────────────

def student_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔍 Проверить баланс",
        callback_data="stu:check_balance",
    )
    builder.button(
        text="✏️ Запросить исправление",
        callback_data="stu:request_edit",
    )
    builder.adjust(1)
    return builder.as_markup()


# ─────────────────────────── РЕГИСТРАЦИЯ: КНОПКА НАЗАД ───────────────────────────

def reg_back_kb() -> InlineKeyboardMarkup:
    """Кнопка «Назад» на шаге ввода имени при регистрации."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data="stu:reg_back")
    return builder.as_markup()