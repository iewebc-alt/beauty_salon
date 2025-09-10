# handlers/booking.py - Самый большой файл, который содержит всю логику конечного
#  автомата (FSM) для процесса записи.
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import date
import httpx
import logging

from fsm import AppointmentStates
from keyboards import create_calendar_keyboard
from services.api_client import api_client

router = Router()

# Шаг 1: /book
@router.message(Command("book"))
async def start_booking(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(AppointmentStates.choosing_service)
    try:
        services = await api_client.get_services()
        builder = InlineKeyboardBuilder()
        for service in services:
            builder.button(text=f"{service['name']} ({service['price']} руб.)", callback_data=f"service_select:{service['id']}:{service['name']}:{service['price']}")
        builder.adjust(1)
        await message.answer("Какую процедуру для вашей красоты выберем сегодня? ✨", reply_markup=builder.as_markup())
    except (httpx.RequestError, httpx.HTTPStatusError):
        await message.answer("Ой, не могу сейчас загрузить список наших прекрасных услуг. Попробуйте, пожалуйста, через минутку! 😔")
        await state.clear()

# Шаг 2: Выбор услуги
@router.callback_query(AppointmentStates.choosing_service, F.data.startswith("service_select:"))
async def service_selected(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":", 3)
    service_id, service_name, service_price = int(parts[1]), parts[2], parts[3]
    await state.update_data(service_id=service_id, service_name=service_name, service_price=service_price)
    try:
        masters = await api_client.get_masters_for_service(service_id)
        if not masters:
            await callback.message.edit_text("К сожалению, на эту услугу сейчас нет свободных мастеров. Может, выберете другую? 💖")
            await state.clear()
            return
        builder = InlineKeyboardBuilder()
        if len(masters) > 1:
            builder.button(text="Любой свободный мастер", callback_data="master_select:any:Любой мастер")
        for master in masters:
            builder.button(text=master['name'], callback_data=f"master_select:{master['id']}:{master['name']}")
        builder.button(text="◀️ Назад к услугам", callback_data="back_to_service")
        builder.adjust(1)
        await callback.message.edit_text("Отличный выбор! ✨ Теперь давайте подберем для вас мастера:", reply_markup=builder.as_markup())
        await state.set_state(AppointmentStates.choosing_master)
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("Простите, не могу загрузить список наших замечательных мастеров. Пожалуйста, попробуйте еще раз. 🙏")
        await state.clear()
    finally:
        await callback.answer()

# Шаг 3: Выбор мастера
@router.callback_query(AppointmentStates.choosing_master, F.data.startswith("master_select:"))
async def master_selected_show_calendar(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":", 2)
    master_id_str, master_name = parts[1], parts[2]
    master_id = None if master_id_str == 'any' else int(master_id_str)
    await state.update_data(master_id=master_id, master_name=master_name)
    today = date.today()
    user_data = await state.get_data()
    try:
        active_days = await api_client.get_active_days(user_data['service_id'], today.year, today.month, master_id)
        calendar_kb = create_calendar_keyboard(today.year, today.month, set(active_days))
        back_button = types.InlineKeyboardButton(text="◀️ Назад к мастерам", callback_data="back_to_master")
        calendar_kb.inline_keyboard.append([back_button])
        await callback.message.edit_text("Прекрасно! Теперь выберите удобную для вас дату в календаре: 🗓️", reply_markup=calendar_kb)
        await state.set_state(AppointmentStates.choosing_date)
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("Произошла ошибка при загрузке календаря. Попробуйте снова.")
    finally:
        await callback.answer()

# Шаг 4: Выбор даты
@router.callback_query(AppointmentStates.choosing_date, F.data.startswith("cal_day:"))
async def process_date_selected(callback: types.CallbackQuery, state: FSMContext):
    _, year, month, day = callback.data.split(":")
    selected_date = date(int(year), int(month), int(day))
    await state.update_data(selected_date=selected_date.isoformat())
    user_data = await state.get_data()
    try:
        slots = await api_client.get_available_slots(user_data['service_id'], selected_date.isoformat(), user_data.get('master_id'))
        if not slots:
            await callback.answer("На эту дату, к сожалению, уже всё расписано. Посмотрите, пожалуйста, другой денёк. 😔", show_alert=True)
            return
        builder = InlineKeyboardBuilder()
        time_buttons = [types.InlineKeyboardButton(text=slot['time'], callback_data=f"time_select:{slot['time']}:{slot['master_id']}") for slot in slots]
        builder.add(*time_buttons)
        builder.row(types.InlineKeyboardButton(text="◀️ Назад к датам", callback_data="back_to_date"))
        builder.adjust(4)
        await callback.message.edit_text("Нашла свободные окошки на этот день! Выбирайте удобное время: 🕒", reply_markup=builder.as_markup())
        await state.set_state(AppointmentStates.choosing_time)
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("Ой, что-то пошло не так при поиске свободного времени. Давайте попробуем еще разок! 😥")
        await state.clear()
    finally:
        await callback.answer()

# Шаг 5: Выбор времени
@router.callback_query(AppointmentStates.choosing_time, F.data.startswith("time_select:"))
async def time_selected(callback: types.CallbackQuery, state: FSMContext):
    try:
        parts = callback.data.split(':')
        selected_time, selected_master_id = f"{parts[1]}:{parts[2]}", int(parts[3])
        await state.update_data(selected_time=selected_time, final_master_id=selected_master_id)
        user_data = await state.get_data()
        master_name = user_data['master_name']
        if user_data.get('master_id') is None:
            all_masters_list = await api_client.get_all_masters()
            all_masters = {master['id']: master['name'] for master in all_masters_list}
            master_name = all_masters.get(selected_master_id, f"Мастер ID {selected_master_id}")

        selected_date_obj = date.fromisoformat(user_data['selected_date'])
        formatted_date = selected_date_obj.strftime("%d %B %Y")

        confirmation_text = (
            f"Почти готово! Давайте всё проверим: 🥰\n\n"
            f"✨ **Услуга:** {user_data['service_name']} ({user_data['service_price']} руб.)\n"
            f"👩‍⚕️ **Мастер:** {master_name}\n"
            f"🗓️ **Дата:** {formatted_date}\n"
            f"🕒 **Время:** {selected_time}\n\n"
            "Всё верно?"
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Да, подтвердить", callback_data="confirm_booking")
        builder.button(text="◀️ Назад к выбору времени", callback_data="back_to_time")
        builder.adjust(1)
        await callback.message.edit_text(confirmation_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        await state.set_state(AppointmentStates.confirmation)
    except Exception as e:
        logging.error(f"CRITICAL ERROR in [time_selected]: {e}", exc_info=True)
        await callback.answer("Ой, произошла какая-то внутренняя ошибка. Пожалуйста, начните сначала. /book 🙏", show_alert=True)
        await state.clear()
    finally:
        await callback.answer()

# Навигация по календарю
@router.callback_query(AppointmentStates.choosing_date, F.data.startswith("cal_nav:"))
async def process_calendar_nav(callback: types.CallbackQuery, state: FSMContext):
    _, year_str, month_str = callback.data.split(":")
    year, month = int(year_str), int(month_str)
    user_data = await state.get_data()
    try:
        active_days = await api_client.get_active_days(user_data['service_id'], year, month, user_data.get('master_id'))
        calendar_kb = create_calendar_keyboard(year, month, set(active_days))
        back_button = types.InlineKeyboardButton(text="◀️ Назад к мастерам", callback_data="back_to_master")
        calendar_kb.inline_keyboard.append([back_button])
        await callback.message.edit_reply_markup(reply_markup=calendar_kb)
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.answer("Не удалось обновить календарь. Попробуйте снова.", show_alert=True)
    finally:
        await callback.answer()

# --- ОБРАБОТЧИКИ "НАЗАД" ---
@router.callback_query(StateFilter(AppointmentStates.choosing_master), F.data == "back_to_service")
async def back_to_service_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AppointmentStates.choosing_service)
    try:
        services = await api_client.get_services()
        builder = InlineKeyboardBuilder()
        for service in services:
            builder.button(text=f"{service['name']} ({service['price']} руб.)", callback_data=f"service_select:{service['id']}:{service['name']}:{service['price']}")
        builder.adjust(1)
        await callback.message.edit_text("Какую процедуру для вашей красоты выберем сегодня? ✨", reply_markup=builder.as_markup())
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("Ой, не могу сейчас загрузить список наших прекрасных услуг. Попробуйте, пожалуйста, через минутку! 😔")
        await state.clear()
    await callback.answer()

@router.callback_query(StateFilter(AppointmentStates.choosing_date), F.data == "back_to_master")
async def back_to_master_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AppointmentStates.choosing_master)
    user_data = await state.get_data()
    try:
        masters = await api_client.get_masters_for_service(user_data['service_id'])
        builder = InlineKeyboardBuilder()
        if len(masters) > 1:
            builder.button(text="Любой свободный мастер", callback_data="master_select:any:Любой мастер")
        for master in masters:
            builder.button(text=master['name'], callback_data=f"master_select:{master['id']}:{master['name']}")
        builder.button(text="◀️ Назад к услугам", callback_data="back_to_service")
        builder.adjust(1)
        await callback.message.edit_text("Хорошо, давайте выберем другого мастера:", reply_markup=builder.as_markup())
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("Простите, не могу загрузить список мастеров. Попробуйте, пожалуйста, еще раз. 🙏")
        await state.clear()
    await callback.answer()

@router.callback_query(StateFilter(AppointmentStates.choosing_time), F.data == "back_to_date")
async def back_to_date_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AppointmentStates.choosing_date)
    user_data = await state.get_data()
    selected_date_obj = date.fromisoformat(user_data['selected_date'])
    try:
        active_days = await api_client.get_active_days(user_data['service_id'], selected_date_obj.year, selected_date_obj.month, user_data.get('master_id'))
        calendar_kb = create_calendar_keyboard(selected_date_obj.year, selected_date_obj.month, set(active_days))
        back_button = types.InlineKeyboardButton(text="◀️ Назад к мастерам", callback_data="back_to_master")
        calendar_kb.inline_keyboard.append([back_button])
        await callback.message.edit_text("Хорошо, давайте выберем другую дату: 🗓️", reply_markup=calendar_kb)
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("Произошла ошибка при возврате к календарю.")
    await callback.answer()

@router.callback_query(StateFilter(AppointmentStates.confirmation), F.data == "back_to_time")
async def back_to_time_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AppointmentStates.choosing_time)
    user_data = await state.get_data()
    try:
        slots = await api_client.get_available_slots(user_data['service_id'], user_data['selected_date'], user_data.get('master_id'))
        builder = InlineKeyboardBuilder()
        time_buttons = [types.InlineKeyboardButton(text=slot['time'], callback_data=f"time_select:{slot['time']}:{slot['master_id']}") for slot in slots]
        builder.add(*time_buttons)
        builder.row(types.InlineKeyboardButton(text="◀️ Назад к датам", callback_data="back_to_date"))
        builder.adjust(4)
        await callback.message.edit_text("Выберите удобное время:", reply_markup=builder.as_markup())
    except Exception as e:
        logging.error(f"Ошибка в back_to_time: {e}")
        await callback.message.edit_text("😔 Ошибка при возврате к выбору времени. Попробуйте отменить /cancel и начать заново.")
        await state.clear()
    await callback.answer()

# --- Финал ---
@router.callback_query(AppointmentStates.confirmation, F.data == "confirm_booking")
async def confirm_booking_handler(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    payload = {
        "telegram_user_id": callback.from_user.id,
        "user_name": callback.from_user.full_name,
        "service_id": user_data['service_id'],
        "master_id": user_data['final_master_id'],
        "start_time": f"{user_data['selected_date']}T{user_data['selected_time']}:00"
    }
    try:
        api_response = await api_client.create_appointment(payload)
        selected_date_obj = date.fromisoformat(user_data['selected_date'])
        formatted_date = selected_date_obj.strftime("%d %B %Y")
        await callback.message.edit_text(
            f"🎉 Ура! Я вас записала! \n\n"
            f"Будем с нетерпением ждать вас в салоне «Элеганс» {formatted_date} в {user_data['selected_time']} "
            f"на процедуру «{api_response['service_name']}» к мастеру {api_response['master_name']}. 💖"
        )
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
        await callback.message.answer(
            "Чтобы мы могли оперативно с вами связаться в случае изменений, поделитесь, пожалуйста, вашим контактным номером телефона. Это очень удобно! 😊",
            reply_markup=keyboard
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            await callback.message.edit_text("😔 Ой, простите, кто-то оказался чуточку быстрее и только что занял это время! Давайте попробуем подобрать другое. Начните, пожалуйста, заново с выбора услуги /book.")
        else:
            await callback.message.edit_text("😔 Простите, произошла какая-то ошибка и запись не была создана. Давайте попробуем еще раз! /book")
            logging.error(f"API Error: {e.response.text}")
    except httpx.RequestError:
        await callback.message.edit_text("😔 Наш сервис записи временно прилег отдохнуть. Попробуйте, пожалуйста, через несколько минут!")
    finally:
        await state.clear()
        await callback.answer()

@router.callback_query(StateFilter(AppointmentStates.confirmation), F.data == "cancel_booking")
async def cancel_booking_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Запись отменена. Если передумаете, я всегда здесь, чтобы помочь! 😊 /book")
    await callback.answer()
