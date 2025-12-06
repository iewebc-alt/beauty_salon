from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder # <-- Добавили
from services.api_client import api_client
from services.yandex_client import yandex_gpt_client
from datetime import datetime
import httpx
import logging

from fsm import AppointmentStates

router = Router()

@router.callback_query(F.data.in_({"ignore", "ignore_inactive_day"}))
async def ignore_callback_handler(callback: types.CallbackQuery):
    await callback.answer("Ой, на этот день уже всё занято, выберите, пожалуйста, другой 😔", show_alert=True)

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext, salon_token: str):
    await state.clear()
    await message.answer(
        f"Здравствуйте, {message.from_user.full_name}! ✨\n"
        "Я — ваш виртуальный администратор. Рада помочь вам!\n\n"
        "Чем могу быть полезна?\n"
        "/book - Записаться через кнопки 💅\n"
        "/my_appointments - Мои записи 🗓️\n\n"
        "Или просто напишите: *'Хочу на стрижку завтра в 10'*",
        parse_mode="Markdown"
    )

@router.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Сейчас нет активного действия. 😊")
        return
    await state.clear()
    await message.answer("Действие отменено. Чем могу помочь? /book")

@router.message(F.contact)
async def handle_contact(message: types.Message, salon_token: str):
    try:
        await api_client.update_client_phone(message.from_user.id, message.contact.phone_number, token=salon_token)
        await message.answer("Спасибо! Номер сохранен, администратор свяжется с вами при необходимости. 😊", reply_markup=types.ReplyKeyboardRemove())
    except Exception:
        await message.answer("Спасибо! Принято.", reply_markup=types.ReplyKeyboardRemove())

# --- ОБРАБОТКА ТЕКСТА (ИИ) ---
@router.message(StateFilter(None))
async def handle_unhandled_content(message: types.Message, state: FSMContext, bot: Bot, salon_token: str):
    await bot.send_chat_action(message.chat.id, 'typing')

    response = await yandex_gpt_client.generate_response_or_tool_call(
        state=state,
        user_message=message.text,
        user_name=message.from_user.full_name
    )

    if response['type'] == 'text':
        # Если это просто текст — отправляем
        await message.answer(response['content'])

    elif response['type'] == 'tool_call':
        # ИИ хочет записать клиента!
        # НО МЫ НЕ ЗАПИСЫВАЕМ СРАЗУ. МЫ СПРАШИВАЕМ ПОДТВЕРЖДЕНИЕ.
        
        tool_args = response['args']
        
        # Сохраняем данные, которые предложил ИИ, в состояние FSM
        await state.update_data(ai_booking_data=tool_args)
        
        # Формируем красивый текст для проверки
        text = (
            "📝 **Проверьте детали записи:**\n\n"
            f"🔹 **Услуга:** {tool_args.get('service_name')}\n"
            f"🔹 **Мастер:** {tool_args.get('master_name', 'Любой')}\n"
            f"🔹 **Дата:** {tool_args.get('appointment_date')}\n"
            f"🔹 **Время:** {tool_args.get('appointment_time')}\n\n"
            "Всё верно?"
        )
        
        # Кнопки подтверждения
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Да, записаться", callback_data="ai_confirm")
        builder.button(text="❌ Нет, изменить", callback_data="ai_cancel")
        builder.adjust(1)

        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        
        # Переводим бота в режим ожидания клика по кнопке
        await state.set_state(AppointmentStates.confirmation) # Используем существующее состояние

# --- ОБРАБОТЧИК КНОПКИ ПОДТВЕРЖДЕНИЯ (ДЛЯ ИИ) ---
@router.callback_query(StateFilter(AppointmentStates.confirmation), F.data == "ai_confirm")
async def ai_confirm_handler(callback: types.CallbackQuery, state: FSMContext, salon_token: str):
    data = await state.get_data()
    tool_args = data.get("ai_booking_data")
    
    if not tool_args:
        await callback.message.edit_text("Ошибка данных. Попробуйте снова.")
        await state.clear()
        return

    # Формируем запрос к API
    payload = {
        "telegram_user_id": callback.from_user.id,
        "user_name": callback.from_user.full_name,
        **tool_args
    }
    
    try:
        # 1. Пытаемся создать запись
        api_response = await api_client.create_natural_appointment(payload, token=salon_token)
        
        dt_object = datetime.fromisoformat(api_response['start_time'])
        formatted_datetime = dt_object.strftime('%d %B в %H:%M')
        
        await callback.message.edit_text(
            f"🎉 **Запись подтверждена!**\n\n"
            f"Ждем вас **{formatted_datetime}**\n"
            f"Мастер: {api_response['master_name']}\n"
            f"Услуга: {api_response['service_name']}",
            parse_mode="Markdown"
        )
        
        # 2. ПРОВЕРЯЕМ, ЗНАЕМ ЛИ МЫ ТЕЛЕФОН
        client_info = await api_client.get_client_by_tg_id(callback.from_user.id, token=salon_token)
        
        if client_info and client_info.get('phone_number'):
            # Телефон есть — не достаем клиента
            await callback.message.answer(f"Ваш номер для связи: {client_info['phone_number']}. Если он изменился, напишите новый.", parse_mode="Markdown")
        else:
            # Телефона нет — просим мягко
            keyboard = types.ReplyKeyboardMarkup(
                keyboard=[[types.KeyboardButton(text="📱 Оставить номер", request_contact=True)]],
                resize_keyboard=True, one_time_keyboard=True
            )
            await callback.message.answer(
                "Чтобы администратор мог предупредить вас об изменениях, вы можете оставить контактный номер (кнопка внизу).",
                reply_markup=keyboard
            )

    except httpx.HTTPStatusError as e:
        # Обработка ошибки от API (например, занято)
        error_msg = "Не удалось записаться."
        try:
            error_json = e.response.json()
            if "detail" in error_json:
                error_msg = f"⚠️ {error_json['detail']}"
        except:
            pass
        
        await callback.message.edit_text(f"{error_msg}\n\nПопробуйте выбрать другое время: /book")

    except Exception as e:
        logging.error(f"Error in AI confirm: {e}")
        await callback.message.edit_text("😔 Произошла техническая ошибка.")
    
    finally:
        await state.clear()

# --- ОБРАБОТЧИК КНОПКИ ОТМЕНЫ (ДЛЯ ИИ) ---
@router.callback_query(StateFilter(AppointmentStates.confirmation), F.data == "ai_cancel")
async def ai_cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Запись отменена. Скажите, что нужно изменить? (например: 'Тогда давай в 16:00')")
