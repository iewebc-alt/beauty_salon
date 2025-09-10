# handlers/common.py - Здесь будут обработчики общих команд, 
# таких как /start, /cancel, а также обработка контактов и сообщений, 
# не попавших в другие хендлеры.
from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
import httpx
import logging
from datetime import datetime

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
    # Здесь можно будет тоже подключить Gemini с памятью, если понадобится
    await message.answer("Пожалуйста, используйте кнопки для выбора или введите /cancel для отмены.")

@router.message(StateFilter(None))
async def handle_unhandled_content(message: types.Message, state: FSMContext, bot: Bot):
    await bot.send_chat_action(message.chat.id, 'typing')

    gemini_response = await gemini_client.generate_response_or_tool_call(
        state=state, # <--- ИСПРАВЛЕНИЕ ЗДЕСЬ
        user_message=message.text,
        user_name=message.from_user.full_name
    )

    if gemini_response['type'] == 'text':
        await message.answer(gemini_response['content'])

    elif gemini_response['type'] == 'tool_call':
        tool_name = gemini_response['name']
        tool_args = gemini_response['args']

        if tool_name == 'create_appointment':
            payload = {
                "telegram_user_id": message.from_user.id,
                "user_name": message.from_user.full_name,
                **tool_args
            }
            
            try:
                api_response = await api_client.create_natural_appointment(payload)
                dt_object = datetime.fromisoformat(api_response['start_time'])
                formatted_datetime = dt_object.strftime('%d %B в %H:%M')
                
                await message.answer(
                    f"🎉 Отлично! Я успешно записал(а) Вас.\n\n"
                    f"**Услуга:** {api_response['service_name']}\n"
                    f"**Мастер:** {api_response['master_name']}\n"
                    f"**Когда:** {formatted_datetime}\n\n"
                    f"Будем ждать Вас в «Элеганс»!",
                    parse_mode="Markdown"
                )
            except httpx.HTTPStatusError as e:
                error_detail = e.response.json().get("detail", "Неизвестная ошибка API.")
                await message.answer(f"😔 Не удалось создать запись. Причина: {error_detail}")
            except Exception as e:
                logging.error(f"Непредвиденная ошибка при вызове API: {e}")
                await message.answer("😔 Простите, произошла непредвиденная ошибка при создании записи.")
