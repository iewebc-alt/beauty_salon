import logging
import json
import httpx
from datetime import date, timedelta
from aiogram.fsm.context import FSMContext
from config import YANDEX_API_KEY, YANDEX_FOLDER_ID

# URL для запросов к YandexGPT
YANDEX_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# Описание инструмента (сразу в виде JSON)
CREATE_APPOINTMENT_TOOL = {
    "function": {
        "name": "create_appointment",
        "description": "Создает запись клиента на услугу. Использовать ТОЛЬКО когда известны услуга, дата и время.",
        "parameters": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Название услуги, например 'стрижка', 'маникюр'."
                },
                "appointment_date": {
                    "type": "string",
                    "description": f"Дата записи в формате YYYY-MM-DD. Сегодня: {date.today().isoformat()}. Если говорят 'завтра', использовать {(date.today() + timedelta(days=1)).isoformat()}."
                },
                "appointment_time": {
                    "type": "string",
                    "description": "Время записи в формате HH:MM. Например, '15:00'."
                },
                "master_name": {
                    "type": "string",
                    "description": "Имя мастера, если клиент его указал."
                },
            },
            "required": ["service_name", "appointment_date", "appointment_time"]
        }
    }
}

class YandexGptClient:
    def __init__(self, api_key: str, folder_id: str):
        self.api_key = api_key
        self.folder_id = folder_id
        if not api_key or not folder_id:
            logging.warning("Ключи для YandexGPT не найдены!")

    def _prepare_history(self, history_raw: list, user_name: str) -> list:
        # Формируем системный промпт
        messages = [
            {
                "role": "system",
                "text": (
                    "Ты — 'Элеганс-Ассистент', ИИ-администратор салона красоты. "
                    "Твоя задача — помочь клиенту записаться, собрав информацию: 1. Услуга, 2. Дата, 3. Время. "
                    "Анализируй историю, чтобы не спрашивать то, что уже известно. Задавай ОДИН уточняющий вопрос за раз. "
                    "Когда соберешь ВСЕ данные, используй инструмент `create_appointment`. "
                    f"Всегда обращайся к клиенту на 'Вы'. Имя клиента: {user_name}."
                )
            }
        ]
        # Добавляем историю
        for msg in history_raw:
            # Конвертируем наш внутренний формат в формат API Яндекса
            role = "assistant" if msg['role'] == 'model' else "user"
            text = msg['parts'][0]['text']
            messages.append({"role": role, "text": text})
        return messages

    async def generate_response_or_tool_call(self, state: FSMContext, user_message: str, user_name: str) -> dict:
        if not self.api_key:
            return {"type": "text", "content": "Ошибка конфигурации AI."}

        data = await state.get_data()
        history_raw = data.get("chat_history", [])
        
        messages = self._prepare_history(history_raw, user_name)
        messages.append({"role": "user", "text": user_message})

        # Тело запроса
        payload = {
            "modelUri": f"gpt://{self.folder_id}/yandexgpt/latest",
            "completionOptions": {
                "stream": False,
                "temperature": 0.2,
                "maxTokens": "1000"
            },
            "messages": messages,
            "tools": [CREATE_APPOINTMENT_TOOL]
        }

        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "x-folder-id": self.folder_id,
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(YANDEX_GPT_URL, json=payload, headers=headers, timeout=10.0)
                
                if response.status_code != 200:
                    logging.error(f"YandexGPT Error {response.status_code}: {response.text}")
                    return {"type": "text", "content": "Простите, сервис временно недоступен."}

                result = response.json()
                
                # Парсим ответ
                # В REST API структура ответа немного отличается от SDK
                alternatives = result.get("result", {}).get("alternatives", [])
                if not alternatives:
                    return {"type": "text", "content": "Не удалось получить ответ."}
                
                message = alternatives[0].get("message", {})
                
                # Обновляем историю (добавляем вопрос пользователя)
                history_raw.append({'role': 'user', 'parts': [{'text': user_message}]})

                # Проверяем наличие вызова инструмента
                if "toolCalls" in message:
                    tool_call = message["toolCalls"][0]
                    tool_name = tool_call["functionCall"]["name"]
                    args = tool_call["functionCall"]["arguments"] # Это словарь
                    
                    logging.info(f"YandexGPT запросил инструмент: {tool_name} с аргументами: {args}")
                    await state.update_data(chat_history=[])
                    return {"type": "tool_call", "name": tool_name, "args": args}
                else:
                    # Обычный текстовый ответ
                    bot_text = message.get("text", "")
                    history_raw.append({'role': 'model', 'parts': [{'text': bot_text}]})
                    await state.update_data(chat_history=history_raw)
                    return {"type": "text", "content": bot_text}

        except Exception as e:
            logging.error(f"Ошибка при HTTP запросе к YandexGPT: {e}")
            return {"type": "text", "content": "Произошла ошибка связи."}

yandex_gpt_client = YandexGptClient(YANDEX_API_KEY, YANDEX_FOLDER_ID)