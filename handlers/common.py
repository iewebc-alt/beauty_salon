# handlers/common.py
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
        "/cancel - Отменить текущее действие",
        reply_markup=types.ReplyKeyboardRemove()
    )

# --- НАЧАЛО ИЗМЕНЕНИЙ ---
@router.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    
    if current_state is None:
        await message.answer("Сейчас нет активного процесса, который можно было бы отменить. 😊")
        return

    # Проверяем, в каком именно состоянии мы находимся
    if current_state == AppointmentStates.awaiting_contact:
        # Если мы просто ждем контакт, запись уже создана. Отменять нечего.
        await state.clear()
        await message.answer(
            "Хорошо, понял(а) Вас. Ваша запись уже подтверждена. Если захотите ее отменить, воспользуйтесь командой /my_appointments. ✨",
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        # Если мы в процессе записи, то отменяем его
        await state.clear()
        await message.answer(
            "Хорошо, я всё отменила. Давайте начнем заново, если хотите! /book",
            reply_markup=types.ReplyKeyboardRemove()
        )
# --- КОНЕЦ ИЗМЕНЕНИЙ ---

@router.message(F.contact, StateFilter(AppointmentStates.awaiting_contact, None))
async def handle_contact(message: types.Message, state: FSMContext):
    try:
        await api_client.update_client_phone(message.from_user.id, message.contact.phone_number)
        await message.answer("Спасибо! Сохранила ваш номер телефона. Теперь мы сможем с вами связаться, если что-то изменится. 😊", reply_markup=types.ReplyKeyboardRemove())
    except (httpx.RequestError, httpx.HTTPStatusError):
        await message.answer("Простите, не удалось сохранить ваш номер телефона из-за технической ошибки. Попробуйте, пожалуйста, еще раз. 🙏")
    finally:
        await state.clear()

@router.message(F.text, StateFilter(AppointmentStates.awaiting_contact))
async def handle_contact_rejection(message: types.Message, state: FSMContext):
    text = message.text.lower()
    negative_responses = ['нет', 'не', 'не хочу', 'отказ', 'позже']
    question_responses = ['зачем', 'почему', 'для чего']

    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    if any(word in text for word in negative_responses):
        await message.answer(
            "Хорошо, без проблем! Ваша запись уже подтверждена. Если что-то изменится, Вы всегда можете написать нам здесь. До встречи в «Элеганс»! ✨",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.clear()
    
    elif any(word in text for word in question_responses):
        await message.answer(
            "Мы просим номер телефона, чтобы администратор мог оперативно связаться с Вами в случае непредвиденных изменений в расписании мастера (например, если мастер заболел). Это помогает избежать недоразумений и вовремя предложить Вам альтернативу. 😊",
            reply_markup=keyboard
        )

    else:
        await message.answer(
            "Я не совсем понял(а). Пожалуйста, либо поделитесь контактом с помощью кнопки ниже, либо просто напишите 'нет', если не хотите этого делать.",
            reply_markup=keyboard
        )

@router.message(F.text, StateFilter(AppointmentStates))
async def handle_text_while_in_state(message: types.Message, bot: Bot):
    await message.answer("Пожалуйста, используйте кнопки для выбора или введите /cancel для отмены.")

@router.message(StateFilter(None))
async def handle_unhandled_content(message: types.Message, state: FSMContext, bot: Bot):
    msg = None
    try:
        msg = await message.answer("Думаю...")
        gemini_response = await gemini_client.handle_natural_language(
            state=state,
            user_message=message.text,
            user_name=message.from_user.full_name
        )

        if gemini_response['type'] == 'text':
            await bot.edit_message_text(
                text=gemini_response['content'],
                chat_id=message.chat.id,
                message_id=msg.message_id
            )
        elif gemini_response['type'] == 'error':
            await bot.edit_message_text(
                text=gemini_response['content'],
                chat_id=message.chat.id,
                message_id=msg.message_id
            )
        elif gemini_response['type'] == 'tool_call':
            await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
            tool_name = gemini_response['name']
            tool_args = gemini_response['args']
            if tool_name == 'create_appointment':
                payload = {"telegram_user_id": message.from_user.id, "user_name": message.from_user.full_name, **tool_args}
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
                    await message.answer(f"😔 Не удалось создать запись. Причина: {error_detail}\n\nПожалуйста, попробуйте еще раз или воспользуйтесь стандартной записью: /book")
                except Exception as e:
                    logging.error(f"Непредвиденная ошибка при вызове API: {e}")
                    await message.answer("😔 Простите, произошла непредвиденная ошибка. Пожалуйста, воспользуйтесь стандартной записью: /book")
    except Exception as e:
        logging.error(f"Критическая ошибка в хендлере: {e}")
        if msg:
            await bot.edit_message_text(
                text="😔 Простите, в боте произошла критическая ошибка. Мы уже работаем над этим.",
                chat_id=message.chat.id,
                message_id=msg.message_id
            )
