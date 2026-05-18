# 📄 файл: utils/validators.py

import re
from datetime import date, datetime
from typing import Optional

# ─────────────────────────── КОНСТАНТЫ ───────────────────────────

NAME_REGEX = re.compile(r"^[A-Za-zА-Яа-яЁё\s\-\.]+$")
DATE_FMT = "%d.%m.%Y"


# ─────────────────────────── ИМЕНА ───────────────────────────

def validate_name(name: str) -> tuple[bool, str]:
    """
    Возвращает (True, '') если имя валидно,
    иначе (False, 'причина').
    """
    stripped = name.strip()
    if not stripped:
        return False, "Имя не может быть пустым."
    if len(stripped) < 2:
        return False, "Имя слишком короткое (минимум 2 символа)."
    if len(stripped) > 64:
        return False, "Имя слишком длинное (максимум 64 символа)."
    if not NAME_REGEX.match(stripped):
        return False, (
            "Имя может содержать только буквы (кириллица/латиница), "
            "пробелы, дефисы и точку."
        )
    return True, ""


# ─────────────────────────── ДАТЫ ───────────────────────────

def parse_date(raw: str) -> Optional[date]:
    """
    Парсит строку в формате DD.MM.YYYY.
    Возвращает date или None при ошибке.
    """
    try:
        return datetime.strptime(raw.strip(), DATE_FMT).date()
    except ValueError:
        return None


def format_date(d: date) -> str:
    """Форматирует date → 'DD.MM.YYYY'."""
    return d.strftime(DATE_FMT)


def parse_date_range(raw: str) -> tuple[Optional[date], Optional[date], str]:
    """
    Парсит строку вида 'DD.MM.YYYY - DD.MM.YYYY'.
    Возвращает (start, end, error_message).
    error_message пустой при успехе.
    """
    parts = [p.strip() for p in raw.split("-", maxsplit=3)]
    # Обрабатываем случай, когда дефис внутри формата не путает split:
    # 'DD.MM.YYYY - DD.MM.YYYY' → split по ' - '
    raw_stripped = raw.strip()
    # Ищем разделитель ' - ' (с пробелами) или просто '-' между датами
    # Формат всегда DD.MM.YYYY - DD.MM.YYYY → ровно один ' - ' между датами
    match = re.match(
        r"^(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})$",
        raw_stripped,
    )
    if not match:
        return None, None, (
            "Неверный формат. Ожидается: ДД.ММ.ГГГГ - ДД.ММ.ГГГГ\n"
            "Например: 01.06.2025 - 01.07.2025"
        )

    start = parse_date(match.group(1))
    end = parse_date(match.group(2))

    if start is None:
        return None, None, f"Неверная дата начала: {match.group(1)}"
    if end is None:
        return None, None, f"Неверная дата окончания: {match.group(2)}"
    if end <= start:
        return None, None, "Дата окончания должна быть позже даты начала."

    return start, end, ""


# ─────────────────────────── КУЛДАУН ───────────────────────────

def cooldown_remaining(last_time_iso: Optional[str], hours: int = 24) -> Optional[str]:
    """
    Принимает ISO-строку последнего действия.
    Если кулдаун ещё не истёк — возвращает строку вида 'X ч Y мин Z сек'.
    Если истёк или last_time_iso is None — возвращает None.
    """
    if not last_time_iso:
        return None
    try:
        last_dt = datetime.fromisoformat(last_time_iso)
    except ValueError:
        return None

    from datetime import timedelta
    delta = timedelta(hours=hours) - (datetime.now() - last_dt)
    if delta.total_seconds() <= 0:
        return None

    total_seconds = int(delta.total_seconds())
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h} ч {m} мин {s} сек"