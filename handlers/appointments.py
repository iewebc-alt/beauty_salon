from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
import httpx
import logging

from services.api_client import api_client

router = Router()

@router.message(Command("my_appointments"))
async def show_my_appointments(message: types.Message, salon_token: str):
    try:
        # Передаем токен!
        appointments = await api_client.get_client_appointments(message.from_user.id, token=salon_token)
        
        if not appointments:
            await message.answer("У Вас пока нет предстоящих записей в нашем салоне. Может, запишемся? /book 😊")
            return
            
        await message.answer("Нашла ваши предстоящие визиты:")
        for appt in appointments:
            dt_object = datetime.fromisoformat(appt['start_time'])
            formatted_date = dt_object.strftime('%d %B %Y в %H:%M')
            
            response_text = (
                f"🗓️ *{formatted_date}*\n"
                f"Услуга: {appt['service_name']}\n"
                f"Мастер: {appt['master_name']}"
            )
            # Кнопка отмены
            builder = InlineKeyboardBuilder().button(text="❌ Отменить запись", callback_data=f"cancel_appt:{appt['id']}")
            await message.answer(response_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
            
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logging.error(f"Error fetching appointments: {e}")
        await message.answer("Ой, не удалось загрузить записи. Попробуйте чуть позже! 🙏")

@router.callback_query(F.data.startswith("cancel_appt:"))
async def cancel_appointment_handler(callback: types.CallbackQuery, salon_token: str):
    appointment_id = int(callback.data.split(":")[1])
    try:
        # Передаем токен!
        await api_client.delete_appointment(appointment_id, token=salon_token)
        await callback.message.edit_text("Готово! Ваша запись отменена. Будем ждать вас в другой раз! 💖")
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logging.error(f"Error deleting appointment: {e}")
        await callback.message.edit_text("Что-то пошло не так, и не получилось отменить запись. Пожалуйста, попробуйте еще раз или свяжитесь с нами напрямую. 😥")
    await callback.answer()
