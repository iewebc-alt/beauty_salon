# bot.py
import asyncio
import logging
import locale

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio.client import Redis

from config import BOT_TOKEN, REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, DEBUG
from handlers import common, appointments, booking

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

async def main():
    bot = Bot(token=BOT_TOKEN)
    
    # Настройка Redis Storage
    redis_client = Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD if REDIS_PASSWORD else None
    )
    storage = RedisStorage(redis=redis_client)
    
    dp = Dispatcher(storage=storage)

    dp.include_router(booking.router)
    dp.include_router(appointments.router)
    dp.include_router(common.router)

    await bot.set_my_commands([
        types.BotCommand(command="start", description="Начало работы"),
        types.BotCommand(command="book", description="Записаться на услугу"),
        types.BotCommand(command="my_appointments", description="Мои записи"),
        types.BotCommand(command="cancel", description="Отменить действие"),
    ])

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_TIME, 'Russian_Russia.1251')  # Fallback для Windows/Docker
        except locale.Error:
            logging.warning("Локаль ru_RU не найдена, месяцы могут отображаться на английском.")
    
    asyncio.run(main())
