# bot.py
import asyncio
import logging
import locale

from aiogram import Bot, Dispatcher, types

from config import BOT_TOKEN
from handlers import common, appointments, booking

# --- Настройка логгирования ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Подключаем роутеры из других файлов
    dp.include_router(booking.router)
    dp.include_router(appointments.router)
    # Роутер с "общими" командами должен быть последним,
    # так как он содержит обработчики, которые "ловят" все остальные сообщения.
    dp.include_router(common.router)

    # Установка команд меню
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Начало работы"),
        types.BotCommand(command="book", description="Записаться на услугу"),
        types.BotCommand(command="my_appointments", description="Мои записи"),
        types.BotCommand(command="cancel", description="Отменить действие"),
    ])

    # Запуск поллинга
    # Удаляем необработанные обновления, чтобы бот не отвечал на старые сообщения
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        # Устанавливаем русскую локаль для корректного отображения месяцев
        locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    except locale.Error:
        logging.warning("Локаль ru_RU.UTF-8 не найдена, месяцы могут отображаться на английском.")
    
    asyncio.run(main())
