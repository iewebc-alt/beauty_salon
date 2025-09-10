# handlers/common.py - Здесь будут обработчики общих команд, 
# таких как /start, /cancel, а также обработка контактов и сообщений, 
# не попавших в другие хендлеры.
from aiogram import Router, types, F, Bot
# --- ДОБАВЛЕНА ЭТА СТРОКА ---
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
import httpx
import logging # Добавим логирование для отладки

from fsm import AppointmentStates
from services.api_client import api_client
from services.gemini import gemini_client

router = Router()

@router.callback_query(F.data.in_({"ignore", "ignore_inactive_day"}))
async def ignore_callback_handler(callback: types.CallbackQuery):
    await callback.answer("Ой, на этот день уже всё занято, выберите, пожалуйста, другой 😔", show_alert=True)

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Здравствуйте, {message.from_user.full_name}! ✨\n"
        "Я — ваш виртуальный администратор салона «Элеганс». Рада помочь вам!\n\n"
        "Чем могу быть полезна?\n"
        "/book - Записаться на процедуру 💅\n"
        "/my_appointments - Посмотреть ваши записи 🗓️\n"
        "/cancel - Отменить текущее действие"
    )

@router.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Сейчас нет активного процесса записи, который можно было бы отменить. 😊")
        return
    await state.clear()
    await message.answer("Хорошо, я всё отменила. Давайте начнем заново, если хотите! /book")

@router.message(F.contact)
async def handle_contact(message: types.Message):
    try:
        await api_client.update_client_phone(message.from_user.id, message.contact.phone_number)
        await message.answer("Спасибо! Сохранила ваш номер телефона. Теперь мы сможем с вами связаться, если что-то изменится. 😊", reply_markup=types.ReplyKeyboardRemove())
    except httpx.HTTPStatusError as e:
        logging.error(f"HTTP Error updating phone: {e.response.status_code} - {e.response.text}")
        await message.answer(f"Простите, не удалось сохранить ваш номер телефона из-за технической ошибки (код {e.response.status_code}). Попробуйте, пожалуйста, еще раз. 🙏")
    except httpx.RequestError as e:
        logging.error(f"Request Error updating phone: {e}")
        await message.answer("Простите, не удалось сохранить ваш номер телефона из-за проблем с подключением. Попробуйте, пожалуйста, еще раз. 🙏")
    except Exception as e:
        logging.error(f"Unexpected error updating phone: {e}")
        await message.answer("Простите, произошла непредвиденная ошибка при сохранении номера телефона. Попробуйте, пожалуйста, еще раз. 🙏")

@router.message(F.text, StateFilter(AppointmentStates))
async def handle_text_while_in_state(message: types.Message, bot: Bot):
    await bot.send_chat_action(message.chat.id, 'typing')
    response_text = await gemini_client.generate_fsm_response(message.text)
    await message.answer(response_text)

@router.message(StateFilter(None))
async def handle_unhandled_content(message: types.Message, bot: Bot):
    await bot.send_chat_action(message.chat.id, 'typing')
    response_text = await gemini_client.generate_unhandled_response(message.text)
    await message.answer(response_text)
