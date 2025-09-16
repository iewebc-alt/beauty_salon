# handlers/appointments.py
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
import httpx
import uuid
import logging
from babel.dates import format_datetime

from services.api_client import api_client

router = Router()

@router.message(Command("my_appointments"))
async def show_my_appointments(message: types.Message, state: FSMContext):
    try:
        appointments = await api_client.get_client_appointments(message.from_user.id)
        if not appointments:
            await message.answer("У Вас пока нет предстоящих записей в нашем салоне «Элеганс». Может, запишемся? /book 😊")
            return
        
        await message.answer("Нашла Ваши предстоящие визиты в «Элеганс»:")
        cancellation_data = {}
        for idx, appt in enumerate(appointments, 1):
            dt_object = datetime.fromisoformat(appt['start_time'])
            formatted_datetime = format_datetime(dt_object, 'd MMMM yyyy в HH:mm', locale='ru_RU')
            response_text = (f"🗓️ *{idx}. {formatted_datetime}*\n" f"Услуга: {appt['service_name']}\n" f"Мастер: {appt['master_name']}")
            short_id = str(uuid.uuid4())[:8]
            cancellation_data[short_id] = {"appointment_id": appt['id'], "service_name": appt['service_name'], "master_name": appt['master_name'], "datetime": formatted_datetime}
            builder = InlineKeyboardBuilder().button(text="❌ Отменить запись", callback_data=f"cancel_appt:{short_id}")
            await message.answer(response_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        await state.update_data(cancellation_data=cancellation_data, cancellation_cache=appointments)
    except (httpx.RequestError, httpx.HTTPStatusError):
        await message.answer("Ой, произошла небольшая техническая заминка, и я не могу сейчас посмотреть Ваши записи. Попробуйте, пожалуйста, чуть позже! 🙏")

@router.callback_query(F.data.startswith("cancel_appt:"))
async def cancel_appointment_handler(callback: types.CallbackQuery, state: FSMContext):
    try:
        short_id = callback.data.split(":", 1)[1]
        data = await state.get_data()
        cancellation_data = data.get("cancellation_data", {})
        appt_info = cancellation_data.get(short_id)
        if not appt_info:
            await callback.message.edit_text("Готово! Ваша запись отменена. Будем ждать Вас в «Элеганс» в другой раз! 💖")
            await callback.answer(); return
        appointment_id = appt_info['appointment_id']
        await api_client.delete_appointment(appointment_id)
        confirmation_text = (f"Готово! Ваша запись на услугу:\n\n" f"✨ **{appt_info['service_name']}**\n" f"👩‍⚕️ к мастеру **{appt_info['master_name']}**\n" f"🗓️ на **{appt_info['datetime']}**\n\n" f"успешно отменена. Будем ждать Вас в «Элеганс» в другой раз! 💖")
        await callback.message.edit_text(confirmation_text, parse_mode="Markdown")
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("Что-то пошло не так, и не получилось отменить запись. Пожалуйста, попробуйте еще раз или свяжитесь с нами напрямую. 😥")
    except Exception as e:
        logging.error(f"Ошибка при обработке отмены: {e}")
        await callback.message.edit_text("Произошла ошибка при обработке отмены. Пожалуйста, попробуйте снова.")
    await callback.answer()
