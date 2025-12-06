from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from services.api_client import api_client

class SalonContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем объект бота из контекста
        bot = data.get("bot")
        if not bot:
            return await handler(event, data)

        # Токен текущего бота
        token = bot.token
        
        # Сохраняем токен в data, чтобы хендлеры могли его использовать
        # для запросов к API (как ключ авторизации салона)
        data["salon_token"] = token
        
        # Внедряем токен в api_client для этого контекста (немного магии)
        # В идеале api_client должен передаваться в handler, но для совместимости
        # мы будем явно передавать токен в методы api_client в хендлерах
        
        return await handler(event, data)
