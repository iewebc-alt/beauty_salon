import asyncio
import logging
import locale
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio.client import Redis
from config import BOT_TOKEN, REDIS_HOST, REDIS_PORT
from handlers import common, appointments, booking

logging.basicConfig(level=logging.INFO)

async def main():
    bot = Bot(token=BOT_TOKEN)
    storage = RedisStorage(redis=Redis(host=REDIS_HOST, port=REDIS_PORT))
    dp = Dispatcher(storage=storage)
    dp.include_router(booking.router)
    dp.include_router(appointments.router)
    dp.include_router(common.router)
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Старт"),
        types.BotCommand(command="book", description="Запись"),
        types.BotCommand(command="my_appointments", description="Мои записи"),
        types.BotCommand(command="cancel", description="Отмена")
    ])
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    except: pass
    asyncio.run(main())