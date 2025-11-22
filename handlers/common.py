from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from services.api_client import api_client
from services.yandex_client import yandex_gpt_client
from datetime import datetime
import httpx

router = Router()

@router.message(CommandStart())
async def start(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer("Привет! Я Элеганс-Ассистент. \n/book - Запись кнопочками \nИли просто напишите, что хотите.")

@router.message(Command("cancel"))
async def cancel(m: types.Message, state: FSMContext):
    await state.clear(); await m.answer("Отменено.")

@router.message(StateFilter(None))
async def chat(m: types.Message, state: FSMContext, bot: Bot):
    await bot.send_chat_action(m.chat.id, 'typing')
    resp = await yandex_gpt_client.generate_response_or_tool_call(state, m.text, m.from_user.full_name)
    
    if resp['type'] == 'text':
        await m.answer(resp['content'])
    elif resp['type'] == 'tool_call':
        try:
            payload = {"telegram_user_id": m.from_user.id, "user_name": m.from_user.full_name, **resp['args']}
            res = await api_client.create_natural_appointment(payload)
            dt = datetime.fromisoformat(res['start_time']).strftime('%d %B в %H:%M')
            await m.answer(f"✅ Записала вас на {dt} ({res['service_name']}).")
        except Exception as e:
            await m.answer(f"Ошибка записи: {str(e)}")