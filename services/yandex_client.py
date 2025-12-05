import logging
import json
import httpx
from datetime import date, timedelta
from aiogram.fsm.context import FSMContext
from config import YANDEX_API_KEY, YANDEX_FOLDER_ID

# URL для запросов к YandexGPT
YANDEX_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# Описание инструмента (JSON)
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
        for msg in history_raw:
            role = "assistant" if msg['role'] == 'model' else "user"
            # Защита от пустых сообщений в истории
            text_content = msg['parts'][0].get('text', '')
            if text_content:
                messages.append({"role": role, "text": text_content})
        return messages

    async def generate_response_or_tool_call(self, state: FSMContext, user_message: str, user_name: str) -> dict:
        if not self.api_key:
            return {"type": "text", "content": "Ошибка конфигурации AI."}

        data = await state.get_data()
        history_raw = data.get("chat_history", [])
        
        messages = self._prepare_history(history_raw, user_name)
        messages.append({"role": "user", "text": user_message})

        payload = {
            "modelUri": f"gpt://{self.folder_id}/yandexgpt/latest",
            "completionOptions": {
                "stream": False,
                "temperature": 0.1, # Снизили температуру для большей точности
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
                response = await client.post(YANDEX_GPT_URL, json=payload, headers=headers, timeout=20.0)
                
                if response.status_code != 200:
                    logging.error(f"YandexGPT Error {response.status_code}: {response.text}")
                    return {"type": "text", "content": f"Простите, сервис временно недоступен (Код {response.status_code})."}

                result = response.json()
                
                # Логируем полный ответ для отладки
                logging.info(f"YandexGPT Raw Response: {json.dumps(result, ensure_ascii=False)}")

                alternatives = result.get("result", {}).get("alternatives", [])
                if not alternatives:
                    return {"type": "text", "content": "Не удалось получить ответ от нейросети."}
                
                message = alternatives[0].get("message", {})
                
                # Сохраняем вопрос пользователя в историю
                history_raw.append({'role': 'user', 'parts': [{'text': user_message}]})

                # --- ИСПРАВЛЕННАЯ ЛОГИКА ПОИСКА ИНСТРУМЕНТОВ ---
                # Проверяем и toolCalls (стандарт), и toolCallList (специфика Яндекса)
                tool_calls = message.get("toolCalls") or message.get("toolCallList", {}).get("toolCalls")
                
                if tool_calls:
                    tool_call = tool_calls[0]
                    tool_name = tool_call["functionCall"]["name"]
                    args = tool_call["functionCall"]["arguments"] # В REST API это уже словарь
                    
                    logging.info(f"YandexGPT запросил инструмент: {tool_name} с аргументами: {args}")
                    
                    # Очищаем историю после успешного вызова, чтобы начать новый контекст
                    await state.update_data(chat_history=[])
                    
                    return {"type": "tool_call", "name": tool_name, "args": args}
                
                # Если инструментов нет, берем текст
                bot_text = message.get("text", "")
                
                # Защита от пустого ответа
                if not bot_text:
                    logging.warning("YandexGPT вернул пустой текст и нет вызова инструмента!")
                    return {"type": "text", "content": "Я вас услышал, но мне нужно уточнить детали. Повторите, пожалуйста."}

                history_raw.append({'role': 'model', 'parts': [{'text': bot_text}]})
                await state.update_data(chat_history=history_raw)
                return {"type": "text", "content": bot_text}

        except Exception as e:
            logging.error(f"Ошибка при HTTP запросе к YandexGPT: {e}")
            return {"type": "text", "content": "Произошла ошибка связи."}

yandex_gpt_client = YandexGptClient(YANDEX_API_KEY, YANDEX_FOLDER_ID)