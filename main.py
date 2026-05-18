# 📄 файл: main.py

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ADMIN_ID
from handlers import admin, student
import database as db

# ─────────────────────────── ЛОГИРОВАНИЕ ───────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─────────────────────────── STARTUP / SHUTDOWN ───────────────────────────

async def on_startup(bot: Bot) -> None:
    await db.init_db()
    await db.expire_overdue_subscriptions()
    logger.info("БД инициализирована и просроченные абонементы обновлены.")
    try:
        await bot.send_message(
            ADMIN_ID,
            "🤖 Бот запущен и готов к работе.",
        )
    except Exception as e:
        logger.warning("Не удалось уведомить админа о запуске: %s", e)


async def on_shutdown(bot: Bot) -> None:
    logger.info("Бот остановлен.")


# ─────────────────────────── MAIN ───────────────────────────

async def main() -> None:
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрируем хуки жизненного цикла
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Подключаем роутеры.
    # Роутер админа регистрируем первым — его фильтры строже.
    dp.include_router(admin.router)
    dp.include_router(student.router)

    logger.info("Запуск polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())