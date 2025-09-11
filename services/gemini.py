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

cancel_appointment_func = FunctionDeclaration(name="cancel_appointment", description="Отменяет существующую запись клиента по её уникальному ID.", parameters={"type": "OBJECT", "properties": {"appointment_id": {"type": "INTEGER"}}, "required": ["appointment_id"]})
get_my_appointments_func = FunctionDeclaration(name="get_my_appointments", description="Получает список всех предстоящих записей клиента с их ID.", parameters={"type": "OBJECT", "properties": {}})
get_salon_info_func = FunctionDeclaration(name="get_salon_info", description="Получает актуальный список всех услуг, цен и мастеров.", parameters={"type": "OBJECT", "properties": {}})
check_availability_func = FunctionDeclaration(name="check_availability", description="Проверяет свободные слоты для услуги на дату.", parameters={"type": "OBJECT", "properties": {"service_name": {"type": "STRING"}, "appointment_date": {"type": "STRING"}}, "required": ["service_name", "appointment_date"]})
create_appointment_func = FunctionDeclaration(name="create_appointment", description="Финальное действие. Создает запись в календаре.", parameters={"type": "OBJECT", "properties": {"service_name": {"type": "STRING"}, "appointment_date": {"type": "STRING"}, "appointment_time": {"type": "STRING"}, "master_name": {"type": "STRING"}}, "required": ["service_name", "appointment_date", "appointment_time"]})

agent_tools = Tool(function_declarations=[cancel_appointment_func, get_my_appointments_func, get_salon_info_func, check_availability_func, create_appointment_func])

class GeminiClient:
    def __init__(self, api_key: str):
        self.model = None
        if not api_key: logging.warning("Ключ API для Gemini не найден!")
        else:
            try:
                genai.configure(api_key=api_key)
                system_instruction = (
                    "Ты — 'Элеганс-Агент', ИИ-администратор. Твоя задача — помогать клиенту, ИСКЛЮЧИТЕЛЬНО используя инструменты. "
                    "ТЫ НЕ ДОЛЖЕН ГЕНЕРИРОВАТЬ ТЕКСТОВЫЙ ОТВЕТ, ЕСЛИ МОЖЕШЬ ВЫЗВАТЬ ИНСТРУМЕНТ. "
                    "ПРАВИЛА ОТМЕНЫ ЗАПИСИ: "
                    "1. Получи запрос от клиента (например, 'отмени запись 26 сентября'). "
                    "2. ОБЯЗАТЕЛЬНО вызови `get_my_appointments`, чтобы получить ПОЛНЫЙ список записей клиента с их ID. "
                    "3. Проанализируй список. Если на указанную дату найдена ТОЛЬКО ОДНА запись, СРАЗУ ЖЕ вызови `cancel_appointment` с ее ID. НЕ СПРАШИВАЙ ПОДТВЕРЖДЕНИЯ. "
                    "4. Если на указанную дату найдено НЕСКОЛЬКО записей, задай клиенту УТОЧНЯЮЩИЙ вопрос, перечислив эти записи, и спроси, какую именно отменить. "
                    "5. Получив ответ, СРАЗУ ЖЕ вызови `cancel_appointment` для каждого соответствующего ID. НЕ ГОВОРИ 'Хорошо, отменяю', А СРАЗУ ВЫЗЫВАЙ ИНСТРУМЕНТ. "
                    "НИКОГДА не спрашивай у клиента ID или номер записи. Ты должен сам находить его."
                )
                self.model = genai.GenerativeModel('gemini-1.5-flash-latest', tools=[agent_tools], system_instruction=system_instruction, generation_config=GenerationConfig(temperature=0.0))
                logging.info("AI-Агент Gemini с железной логикой отмены успешно инициализирован.")
            except Exception as e:
                logging.error(f"Не удалось инициализировать Gemini: {e}"); self.model = None

    async def handle_natural_language(self, state: FSMContext, user_message: str, user_name: str, telegram_user_id: int) -> dict:
        if not self.model: return {"type": "error", "content": "Сервис AI временно недоступен."}
        data = await state.get_data(); history_raw = data.get("chat_history", [])
        if not history_raw: history_raw.append({'role': 'user', 'parts': [{'text': f"(Системная заметка: имя клиента - {user_name})"}]})
        chat_session = self.model.start_chat(history=history_raw)
        try:
            response = await asyncio.wait_for(chat_session.send_message_async(user_message), timeout=GEMINI_TIMEOUT)
            while response.parts[0].function_call:
                tool_calls = [part.function_call for part in response.parts if part.function_call]
                if not tool_calls: break
                tool_responses = []
                is_final_action = False
                for tool_call in tool_calls:
                    tool_name = tool_call.name
                    tool_args = {key: value for key, value in tool_call.args.items()}
                    logging.info(f"Агент хочет использовать инструмент: {tool_name} с аргументами: {tool_args}")
                    if tool_name in ["create_appointment", "cancel_appointment"]:
                        is_final_action = True
                        tool_responses.append({"type": "tool_call", "name": tool_name, "args": tool_args})
                        continue
                    tool_response_content = ""
                    if tool_name == "get_my_appointments":
                        api_result = await api_client.get_client_appointments(telegram_user_id)
                        # --- ИСПРАВЛЕНИЕ ЗДЕСЬ: Ключ теперь строка ---
                        cancellation_cache = {str(item['id']): item for item in api_result}
                        await state.update_data(cancellation_cache=cancellation_cache)
                        if not api_result: tool_response_content = "У клиента нет предстоящих записей."
                        else: tool_response_content = f"Вот список записей клиента: {json.dumps(api_result, ensure_ascii=False, default=str)}"
                    elif tool_name == "get_salon_info":
                        api_result = await api_client.get_salon_info(); tool_response_content = json.dumps(api_result, ensure_ascii=False)
                    elif tool_name == "check_availability":
                        api_result = await api_client.check_availability(**tool_args, telegram_user_id=telegram_user_id)
                        if not api_result: tool_response_content = "На эту дату свободных слотов нет."
                        else: tool_response_content = f"Вот список свободных слотов: {json.dumps(api_result, ensure_ascii=False)}"
                    tool_responses.append({"function_response": {"name": tool_name, "response": {"content": tool_response_content}}})
                if is_final_action:
                    await state.update_data(chat_history=[])
                    return {"type": "multi_tool_call", "calls": [r for r in tool_responses if r['type'] == 'tool_call']}
                response = await asyncio.wait_for(chat_session.send_message_async(tool_responses), timeout=GEMINI_TIMEOUT)
            final_text = response.parts[0].text
            updated_history = [{'role': c.role, 'parts': [{'text': p.text} for p in c.parts]} for c in chat_session.history if c.role != 'user' or "(Системная заметка:" not in c.parts[0].text]
            await state.update_data(chat_history=updated_history)
            return {"type": "text", "content": final_text}
        except (asyncio.TimeoutError, Exception) as e:
            logging.error(f"Ошибка при работе с Gemini: {e}")
            if "quota" in str(e).lower(): return {"type": "error", "content": "😔 К сожалению, дневной лимит запросов к AI исчерпан."}
            return {"type": "error", "content": "😔 Простите, произошла внутренняя ошибка ассистента."}

gemini_client = GeminiClient(GEMINI_API_KEY)
