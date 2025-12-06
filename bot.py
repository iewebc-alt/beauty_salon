import asyncio
import logging
import sys
import locale
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio.client import Redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import REDIS_HOST, REDIS_PORT, DATABASE_URL
from middleware import SalonContextMiddleware
import models
from handlers import common, appointments, booking

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

# Функция для проверки количества салонов в базе
def get_active_salons_count():
    try:
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        count = session.query(models.Salon).filter(models.Salon.is_active == True).count()
        session.close()
        return count
    except Exception as e:
        logging.error(f"DB Error check: {e}")
        return 0

async def main():
    # 1. Получаем салоны
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    salons = session.query(models.Salon).filter(models.Salon.is_active == True).all()
    session.close()

    if not salons:
        logging.warning("Нет активных салонов. Ожидание...")
        # Если салонов нет, просто ждем 10 сек и перезапускаемся, вдруг появятся
        await asyncio.sleep(10)
        sys.exit(0) 

    logging.info(f"Найдено активных салонов: {len(salons)}")

    # 2. Инициализация
    storage = RedisStorage(redis=Redis(host=REDIS_HOST, port=REDIS_PORT))
    dp = Dispatcher(storage=storage)
    dp.update.outer_middleware(SalonContextMiddleware())
    
    dp.include_router(booking.router)
    dp.include_router(appointments.router)
    dp.include_router(common.router)

    # 3. Создаем ботов
    bots = []
    for salon in salons:
        try:
            bot = Bot(token=salon.telegram_token)
            await bot.delete_webhook(drop_pending_updates=True)
            # Устанавливаем команды для каждого бота
            await bot.set_my_commands([
                types.BotCommand(command="start", description="Начало"),
                types.BotCommand(command="book", description="Запись"),
                types.BotCommand(command="my_appointments", description="Мои записи"),
                types.BotCommand(command="cancel", description="Отмена")
            ])
            bots.append(bot)
        except Exception as e:
            logging.error(f"Ошибка при запуске бота для {salon.name}: {e}")

    if not bots:
        logging.error("Не удалось запустить ни одного бота.")
        sys.exit(1)

    # 4. Запускаем Polling в фоновом режиме
    polling_task = asyncio.create_task(dp.start_polling(*bots))
    
    # 5. Цикл слежения за новыми салонами (Hot Reload)
    initial_count = len(salons)
    logging.info("Бот запущен. Слежу за изменениями в БД...")
    
    while True:
        await asyncio.sleep(10) # Проверяем каждые 10 секунд
        current_count = get_active_salons_count()
        
        if current_count != initial_count:
            logging.info("Обнаружено изменение количества салонов! Перезагрузка...")
            polling_task.cancel() # Останавливаем текущих ботов
            sys.exit(0) # Завершаем процесс. Docker (restart: always) запустит его заново.

if __name__ == "__main__":
    try:
        locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    except:
        pass
    asyncio.run(main())
