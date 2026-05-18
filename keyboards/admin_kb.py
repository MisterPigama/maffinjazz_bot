# 📄 файл: keyboards/admin_kb.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ─────────────────────────── ГЛАВНОЕ МЕНЮ АДМИНА ───────────────────────────

def admin_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Ученики",         callback_data="adm:students")
    builder.button(text="➕ Новый абонемент",  callback_data="adm:new_sub")
    builder.button(text="📋 Все абонементы",  callback_data="adm:all_subs")
    builder.button(text="✅ Отметить посещение", callback_data="adm:attend")
    builder.adjust(2)
    return builder.as_markup()


# ─────────────────────────── СПИСОК УЧЕНИКОВ ───────────────────────────

def students_list_kb(students: list[dict], action: str) -> InlineKeyboardMarkup:
    """
    action: 'new_sub' | 'edit_sub' | 'view_sub'
    callback_data формат: act:{action}:u{user_id}
    Длина ≤ 64 символов.
    """
    builder = InlineKeyboardBuilder()
    for s in students:
        uid = s["id"]
        name = s["name"]
        # Обрезаем имя в тексте кнопки до 32 символов для читаемости
        label = name if len(name) <= 32 else name[:30] + "…"
        cb = f"act:{action}:u{uid}"
        builder.button(text=label, callback_data=cb)
    builder.button(text="⬅️ Назад", callback_data="adm:back_main")
    builder.adjust(1)
    return builder.as_markup()


# ─────────────────────────── КАРТОЧКА АБОНЕМЕНТА (РЕДАКТИРОВАНИЕ) ───────────────────────────

def subscription_edit_kb(sub_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📅 Изменить даты",
        callback_data=f"act:edit_dates:s{sub_id}",
    )
    builder.button(
        text="🔢 Изменить кол-во занятий",
        callback_data=f"act:edit_lessons:s{sub_id}",
    )
    builder.button(text="⬅️ Назад", callback_data="adm:students_edit")
    builder.adjust(1)
    return builder.as_markup()


# ─────────────────────────── ВЫБОР КОЛ-ВА ЗАНЯТИЙ (1-8) ───────────────────────────

def lessons_choice_kb(sub_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i in range(1, 9):
        builder.button(
            text=str(i),
            callback_data=f"act:set_lessons:s{sub_id}:{i}",
        )
    builder.button(
        text="⬅️ Назад",
        callback_data=f"act:edit_sub:s{sub_id}",
    )
    builder.adjust(4, 4, 1)
    return builder.as_markup()


# ─────────────────────────── ВОПРОС «УЖЕ ПОТРАЧЕНО ЗАНЯТИЕ?» ───────────────────────────

def lesson_spent_kb(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Да",
        callback_data=f"act:spent_yes:u{user_id}",
    )
    builder.button(
        text="❌ Нет",
        callback_data=f"act:spent_no:u{user_id}",
    )
    builder.button(text="⬅️ Назад", callback_data="adm:new_sub")
    builder.adjust(2, 1)
    return builder.as_markup()


# ─────────────────────────── ОТМЕТКА ПОСЕЩЕНИЯ (мульти-выбор) ───────────────────────────

def attend_kb(
    subscriptions: list[dict],
    selected: set[int],
) -> InlineKeyboardMarkup:
    """
    subscriptions: список dict с ключами sub_id, name, lessons_left.
    selected: множество sub_id уже отмеченных.
    callback_data: act:toggle_attend:s{sub_id}
    """
    builder = InlineKeyboardBuilder()
    for sub in subscriptions:
        sid = sub["sub_id"]
        check = "✅ " if sid in selected else "☐ "
        label = f"{check}{sub['name']} ({sub['lessons_left']} зан.)"
        # Обрезаем до 64 символов в тексте кнопки
        if len(label) > 64:
            label = label[:62] + "…"
        builder.button(
            text=label,
            callback_data=f"act:toggle_attend:s{sid}",
        )
    builder.button(
        text="💾 Сохранить",
        callback_data="adm:save_attend",
    )
    builder.button(text="⬅️ Назад", callback_data="adm:back_main")
    builder.adjust(1)
    return builder.as_markup()


# ─────────────────────────── УНИВЕРСАЛЬНАЯ КНОПКА «НАЗАД» ───────────────────────────

def back_to_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В главное меню", callback_data="adm:back_main")
    return builder.as_markup()