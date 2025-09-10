# services/gemini.py
import logging
import asyncio
from datetime import date, timedelta
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, Tool, FunctionDeclaration
from aiogram.fsm.context import FSMContext
from config import GEMINI_API_KEY

GEMINI_TIMEOUT = 15.0

create_appointment_func = FunctionDeclaration(
    name="create_appointment",
    description="Создает запись клиента на услугу в салоне красоты. Используй этот инструмент ТОЛЬКО ТОГДА, когда у тебя есть ВСЯ необходимая информация: услуга, полная дата и точное время.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "service_name": {"type": "STRING", "description": "Название услуги, например 'стрижка', 'маникюр'."},
            "appointment_date": {"type": "STRING", "description": f"Полная дата записи в формате YYYY-MM-DD. Сегодня: {date.today().isoformat()}. Если клиент говорит 'завтра', используй {(date.today() + timedelta(days=1)).isoformat()}."},
            "appointment_time": {"type": "STRING", "description": "Время записи в формате HH:MM. Например, '15:00', '09:30'."},
            "master_name": {"type": "STRING", "description": "Имя мастера, если клиент его указал."},
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
                    "Ты — 'Элеганс-Ассистент', ИИ-администратор салона красоты. Твоя главная задача — помочь клиенту записаться на услугу. "
                    "Веди диалог, чтобы последовательно собрать ТРИ фрагмента информации: 1. Услуга, 2. Дата, 3. Время. "
                    "Анализируй историю чата, чтобы не спрашивать то, что уже известно. Задавай только ОДИН уточняющий вопрос за раз. "
                    "Когда соберешь ВСЕ три фрагмента, используй инструмент `create_appointment`. "
                    "Всегда обращайся к клиенту на 'Вы'. Твой первый ответ в диалоге всегда должен начинаться с приветствия по имени."
                )
                self.model = genai.GenerativeModel(
                    'gemini-1.5-flash-latest',
                    tools=[appointment_tool],
                    system_instruction=system_instruction,
                    generation_config=GenerationConfig(temperature=0.1)
                )
                logging.info("Модель Gemini с единым центром ошибок успешно инициализирована.")
            except Exception as e:
                logging.error(f"Не удалось инициализировать Gemini: {e}")
                self.model = None

    async def handle_natural_language(self, state: FSMContext, user_message: str, user_name: str) -> dict:
        if not self.model:
            return {"type": "error", "content": "Простите, сервис AI временно недоступен. Пожалуйста, воспользуйтесь стандартной записью: /book"}

        data = await state.get_data()
        history_raw = data.get("chat_history", [])
        
        if not history_raw:
            history_raw.append({'role': 'user', 'parts': [{'text': f"(Системная заметка: имя клиента - {user_name})"}]})

        chat_session = self.model.start_chat(history=history_raw)
        
        try:
            response_task = chat_session.send_message_async(user_message)
            response = await asyncio.wait_for(response_task, timeout=GEMINI_TIMEOUT)
            
            response_part = response.parts[0]
            updated_history = [{'role': c.role, 'parts': [{'text': p.text} for p in c.parts]} for c in chat_session.history if c.role != 'user' or "(Системная заметка:" not in c.parts[0].text]
            await state.update_data(chat_history=updated_history)

            if response_part.function_call:
                tool_call = response_part.function_call
                args = {key: value for key, value in tool_call.args.items()}
                logging.info(f"Gemini запросил вызов инструмента: {tool_call.name} с аргументами: {args}")
                await state.update_data(chat_history=[])
                return {"type": "tool_call", "name": tool_call.name, "args": args}
            else:
                return {"type": "text", "content": response_part.text}

        except asyncio.TimeoutError:
            logging.warning(f"Gemini API timeout for user")
            return {"type": "error", "content": "😔 Простите, ассистент долго отвечает. Пожалуйста, попробуйте еще раз через минуту или воспользуйтесь стандартной записью: /book"}
        except Exception as e:
            logging.error(f"Ошибка при работе с Gemini: {e}")
            if "quota" in str(e).lower():
                 return {"type": "error", "content": "😔 К сожалению, дневной лимит запросов к AI исчерпан. Пожалуйста, воспользуйтесь стандартной записью /book или попробуйте завтра."}
            return {"type": "error", "content": "😔 Простите, произошла внутренняя ошибка ассистента. Пожалуйста, воспользуйтесь стандартной записью: /book"}

gemini_client = GeminiClient(GEMINI_API_KEY)
