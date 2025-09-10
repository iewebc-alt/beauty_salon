# handlers/appointments.py - Логика, связанная с просмотром и отменой существующих записей.
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
import httpx

from services.api_client import api_client

router = Router()

@router.message(Command("my_appointments"))
async def show_my_appointments(message: types.Message):
    try:
        appointments = await api_client.get_client_appointments(message.from_user.id)
        if not appointments:
            await message.answer("У вас пока нет предстоящих записей в нашем салоне «Элеганс». Может, запишемся? /book 😊")
            return
        await message.answer("Нашла ваши предстоящие визиты в «Элеганс»:")
        for appt in appointments:
            dt_object = datetime.fromisoformat(appt['start_time'])
            response_text = (
                f"🗓️ *{dt_object.strftime('%d %B %Y в %H:%M')}*\n"
                f"Услуга: {appt['service_name']}\n"
                f"Мастер: {appt['master_name']}"
            )
            builder = InlineKeyboardBuilder().button(text="❌ Отменить запись", callback_data=f"cancel_appt:{appt['id']}")
            await message.answer(response_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    except (httpx.RequestError, httpx.HTTPStatusError):
        await message.answer("Ой, произошла небольшая техническая заминка, и я не могу сейчас посмотреть ваши записи. Попробуйте, пожалуйста, чуть позже! 🙏")

@router.callback_query(F.data.startswith("cancel_appt:"))
async def cancel_appointment_handler(callback: types.CallbackQuery):
    appointment_id = int(callback.data.split(":")[1])
    try:
        await api_client.delete_appointment(appointment_id)
        await callback.message.edit_text("Готово! Ваша запись отменена. Будем ждать вас в «Элеганс» в другой раз! 💖")
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("Что-то пошло не так, и не получилось отменить запись. Пожалуйста, попробуйте еще раз или свяжитесь с нами напрямую. 😥")
    await callback.answer()
