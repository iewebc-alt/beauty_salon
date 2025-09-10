# services/gemini.py
import logging
from datetime import date, timedelta
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, Tool, FunctionDeclaration
from aiogram.fsm.context import FSMContext
from config import GEMINI_API_KEY

create_appointment_func = FunctionDeclaration(
    name="create_appointment",
    description="Создает запись клиента на услугу в салоне красоты. Используй этот инструмент ТОЛЬКО ТОГДА, когда у тебя есть ВСЯ необходимая информация: услуга, полная дата и точное время.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "service_name": {
                "type": "STRING",
                "description": "Название услуги, например 'стрижка', 'маникюр'."
            },
            "appointment_date": {
                "type": "STRING",
                "description": f"Полная дата записи в формате YYYY-MM-DD. Сегодня: {date.today().isoformat()}. Если клиент говорит 'завтра', используй {(date.today() + timedelta(days=1)).isoformat()}."
            },
            "appointment_time": {
                "type": "STRING",
                "description": "Время записи в формате HH:MM. Например, '15:00', '09:30'."
            },
            "master_name": {
                "type": "STRING",
                "description": "Имя мастера, если клиент его указал."
            },
        },
        "required": ["service_name", "appointment_date", "appointment_time"]
    },
)
appointment_tool = Tool(function_declarations=[create_appointment_func])


class GeminiClient:
    def __init__(self, api_key: str):
        self.model = None
        if not api_key:
            logging.warning("Ключ API для Gemini (GEMINI_API_KEY) не найден!")
        else:
            try:
                genai.configure(api_key=api_key)
                system_instruction = (
                    "Ты — 'Элеганс-Ассистент', ИИ-администратор салона красоты. "
                    "Твоя главная задача — помочь клиенту записаться на услугу. "
                    "Ты должен вести диалог, чтобы последовательно собрать ТРИ фрагмента информации: 1. Услуга, 2. Дата, 3. Время. "
                    "Анализируй историю чата, чтобы не спрашивать то, что уже известно. "
                    "Задавай только ОДИН уточняющий вопрос за раз. Будь кратким и вежливым. "
                    "Когда соберешь ВСЕ три фрагмента, используй инструмент `create_appointment`. "
                    "Всегда обращайся к клиенту на 'Вы'."
                )
                self.model = genai.GenerativeModel(
                    'gemini-1.5-flash-latest',
                    tools=[appointment_tool],
                    system_instruction=system_instruction,
                    generation_config=GenerationConfig(temperature=0.1)
                )
                logging.info("Модель Gemini с улучшенной памятью успешно инициализирована.")
            except Exception as e:
                logging.error(f"Не удалось инициализировать Gemini: {e}")
                self.model = None

    async def generate_response_or_tool_call(self, state: FSMContext, user_message: str, user_name: str) -> dict:
        if not self.model:
            return {"type": "text", "content": "Простите, у меня временные технические неполадки."}

        data = await state.get_data()
        history_raw = data.get("chat_history", [])
        
        if not history_raw:
            history_raw.append({'role': 'user', 'parts': [{'text': f"(Системная заметка: имя клиента - {user_name})"}]})
            history_raw.append({'role': 'model', 'parts': [{'text': f"Здравствуйте, {user_name}! Чем могу Вам помочь?"}]})

        chat_session = self.model.start_chat(history=history_raw)

        try:
            response = await chat_session.send_message_async(user_message)
            response_part = response.parts[0]

            updated_history = []
            for content in chat_session.history:
                if "(Системная заметка:" in content.parts[0].text:
                    continue
                updated_history.append({
                    'role': content.role,
                    'parts': [{'text': part.text} for part in content.parts]
                })

            await state.update_data(chat_history=updated_history)

            if response_part.function_call:
                tool_call = response_part.function_call
                # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
                args = {key: value for key, value in tool_call.args.items()}
                logging.info(f"Gemini запросил вызов инструмента: {tool_call.name} с аргументами: {args}")
                await state.update_data(chat_history=[])
                return {"type": "tool_call", "name": tool_call.name, "args": args}
            else:
                return {"type": "text", "content": response_part.text}

        except Exception as e:
            logging.error(f"Ошибка при работе с Gemini: {e}")
            return {"type": "text", "content": "Простите, произошла ошибка. Попробуйте еще раз."}

gemini_client = GeminiClient(GEMINI_API_KEY)
