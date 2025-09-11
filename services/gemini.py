# services/gemini.py
import logging
import json
import asyncio
from datetime import date, timedelta
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, Tool, FunctionDeclaration
from aiogram.fsm.context import FSMContext
from config import GEMINI_API_KEY
from services.api_client import api_client

GEMINI_TIMEOUT = 20.0

get_salon_info_func = FunctionDeclaration(name="get_salon_info", description="Получает актуальный список всех услуг, цен, мастеров и их специализаций.", parameters={"type": "OBJECT", "properties": {}})
check_availability_func = FunctionDeclaration(name="check_availability", description="Проверяет свободные слоты для конкретной услуги на конкретную дату.", parameters={"type": "OBJECT", "properties": {"service_name": {"type": "STRING", "description": "Точное название услуги, например 'Женская стрижка'."},"appointment_date": {"type": "STRING", "description": f"Дата для проверки в формате YYYY-MM-DD. Сегодня: {date.today().isoformat()}."}}, "required": ["service_name", "appointment_date"]})
create_appointment_func = FunctionDeclaration(name="create_appointment", description="Финальное действие. Создает запись в календаре.", parameters={"type": "OBJECT", "properties": {"service_name": {"type": "STRING", "description": "Название услуги."},"appointment_date": {"type": "STRING", "description": "Дата записи в формате YYYY-MM-DD."},"appointment_time": {"type": "STRING", "description": "Время записи в формате HH:MM."},"master_name": {"type": "STRING", "description": "Имя мастера, если оно известно."}}, "required": ["service_name", "appointment_date", "appointment_time"]})
agent_tools = Tool(function_declarations=[get_salon_info_func, check_availability_func, create_appointment_func])

class GeminiClient:
    def __init__(self, api_key: str):
        self.model = None
        if not api_key: logging.warning("Ключ API для Gemini не найден!")
        else:
            try:
                genai.configure(api_key=api_key)
                system_instruction = ("Ты — 'Элеганс-Агент', умный ИИ-администратор. Твоя задача — помочь клиенту записаться, используя инструменты. " "Твой рабочий процесс: 1. Если нужно, используй `get_salon_info`, чтобы узнать об услугах. " "2. Когда клиент выберет услугу и дату, ОБЯЗАТЕЛЬНО используй `check_availability`, чтобы найти свободные слоты. " "3. Предложи найденные слоты клиенту. " "4. Когда клиент выберет конкретное время, используй `create_appointment` для записи. " "Не придумывай информацию, всегда получай ее через инструменты.")
                self.model = genai.GenerativeModel('gemini-1.5-flash-latest', tools=[agent_tools], system_instruction=system_instruction, generation_config=GenerationConfig(temperature=0.1))
                logging.info("AI-Агент Gemini успешно инициализирован.")
            except Exception as e:
                logging.error(f"Не удалось инициализировать Gemini: {e}"); self.model = None

    async def handle_natural_language(self, state: FSMContext, user_message: str, user_name: str) -> dict:
        if not self.model: return {"type": "error", "content": "Сервис AI временно недоступен."}
        data = await state.get_data(); history_raw = data.get("chat_history", [])
        if not history_raw: history_raw.append({'role': 'user', 'parts': [{'text': f"(Системная заметка: имя клиента - {user_name})"}]})
        chat_session = self.model.start_chat(history=history_raw)
        try:
            for _ in range(5):
                response_task = chat_session.send_message_async(user_message if _ == 0 else "")
                response = await asyncio.wait_for(response_task, timeout=GEMINI_TIMEOUT)
                response_part = response.parts[0]
                if response_part.function_call:
                    tool_call = response_part.function_call; tool_name = tool_call.name; tool_args = {key: value for key, value in tool_call.args.items()}
                    logging.info(f"Агент хочет использовать инструмент: {tool_name} с аргументами: {tool_args}")
                    tool_response_content = ""
                    if tool_name == "get_salon_info":
                        api_result = await api_client.get_salon_info(); tool_response_content = json.dumps(api_result, ensure_ascii=False)
                    elif tool_name == "check_availability":
                        api_result = await api_client.check_availability(**tool_args)
                        if not api_result: tool_response_content = "На эту дату свободных слотов нет. Предложи клиенту выбрать другую дату."
                        else: tool_response_content = f"Вот список свободных слотов: {json.dumps(api_result, ensure_ascii=False)}"
                    elif tool_name == "create_appointment":
                        await state.update_data(chat_history=[]); return {"type": "tool_call", "name": tool_name, "args": tool_args}
                    tool_response_part = {"function_response": {"name": tool_name, "response": {"content": tool_response_content}}}
                    response = await chat_session.send_message_async(tool_response_part)
                else:
                    updated_history = [{'role': c.role, 'parts': [{'text': p.text} for p in c.parts]} for c in chat_session.history if c.role != 'user' or "(Системная заметка:" not in c.parts[0].text]
                    await state.update_data(chat_history=updated_history); return {"type": "text", "content": response_part.text}
            return {"type": "error", "content": "Ассистент зашел в тупик. Пожалуйста, попробуйте сформулировать запрос проще или воспользуйтесь /book."}
        except (asyncio.TimeoutError, Exception) as e:
            logging.error(f"Ошибка при работе с Gemini: {e}")
            if "quota" in str(e).lower(): return {"type": "error", "content": "😔 К сожалению, дневной лимит запросов к AI исчерпан. Пожалуйста, воспользуйтесь стандартной записью /book или попробуйте завтра."}
            return {"type": "error", "content": "😔 Простите, произошла внутренняя ошибка ассистента. Пожалуйста, воспользуйтесь стандартной записью: /book"}

gemini_client = GeminiClient(GEMINI_API_KEY)
