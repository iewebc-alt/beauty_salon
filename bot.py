import asyncio
import logging
import httpx
import calendar
from datetime import datetime, date
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import BOT_TOKEN, API_URL

# --- Настройка ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
if not BOT_TOKEN:
    logging.critical("Не удалось загрузить токен бота! Проверьте .env файл.")
    exit("Bot token not found!")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- FSM ---
class AppointmentStates(StatesGroup):
    choosing_service = State()
    choosing_master = State()
    choosing_date = State()
    choosing_time = State()
    confirmation = State()

# --- Календарь ---
def create_calendar_keyboard(year: int, month: int, active_days: set = None) -> types.InlineKeyboardMarkup:
    if active_days is None: active_days = set()
    builder = InlineKeyboardBuilder()
    month_name = calendar.month_name[month]
    builder.row(types.InlineKeyboardButton(text=f"{month_name} {year}", callback_data="ignore"))
    days_of_week = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    builder.row(*[types.InlineKeyboardButton(text=day, callback_data="ignore") for day in days_of_week])
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row_buttons = []
        for day in week:
            if day == 0: row_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
            elif day in active_days:
                row_buttons.append(types.InlineKeyboardButton(text=f"[{day}]", callback_data=f"cal_day:{year}:{month}:{day}"))
            else:
                row_buttons.append(types.InlineKeyboardButton(text=str(day), callback_data="ignore_inactive_day"))
        builder.row(*row_buttons)
    prev_month, prev_year = (month - 1, year) if month > 1 else (12, year - 1)
    next_month, next_year = (month + 1, year) if month < 12 else (1, year + 1)
    builder.row(
        types.InlineKeyboardButton(text="< Назад", callback_data=f"cal_nav:{prev_year}:{prev_month}"),
        types.InlineKeyboardButton(text="Вперед >", callback_data=f"cal_nav:{next_year}:{next_month}")
    )
    return builder.as_markup()

@dp.callback_query(F.data.in_({"ignore", "ignore_inactive_day"}))
async def ignore_callback_handler(callback: types.CallbackQuery): await callback.answer("На этот день записи нет.", show_alert=True)

# --- Команды ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(f"Здравствуйте, {message.from_user.full_name}!\nДоступные команды:\n/book - Записаться\n/my_appointments - Мои записи\n/cancel - Отмена")

@dp.message(Command("my_appointments"))
async def show_my_appointments(message: types.Message):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/clients/{message.from_user.id}/appointments"); response.raise_for_status()
        appointments = response.json()
        if not appointments: await message.answer("У вас нет предстоящих записей."); return
        await message.answer("Ваши предстоящие записи:")
        for appt in appointments:
            dt_object = datetime.fromisoformat(appt['start_time'])
            response_text = (f"🗓 *{dt_object.strftime('%d %B %Y в %H:%M')}*\n"
                             f"Услуга: {appt['service_name']}\nМастер: {appt['master_name']}")
            builder = InlineKeyboardBuilder().button(text="❌ Отменить", callback_data=f"cancel_appt:{appt['id']}")
            await message.answer(response_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    except (httpx.RequestError, httpx.HTTPStatusError):
        await message.answer("😔 Не удалось загрузить список записей.")

@dp.callback_query(F.data.startswith("cancel_appt:"))
async def cancel_appointment_handler(callback: types.CallbackQuery):
    appointment_id = int(callback.data.split(":")[1])
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(f"{API_URL}/api/v1/appointments/{appointment_id}"); response.raise_for_status()
        await callback.message.edit_text("✅ Ваша запись успешно отменена.")
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("😔 Не удалось отменить запись.")
    await callback.answer()

@dp.message(F.contact)
async def handle_contact(message: types.Message):
    try:
        payload = {"phone_number": message.contact.phone_number}
        async with httpx.AsyncClient() as client:
            response = await client.patch(f"{API_URL}/api/v1/clients/{message.from_user.id}", json=payload); response.raise_for_status()
        await message.answer("Спасибо! Ваш номер телефона сохранен.", reply_markup=types.ReplyKeyboardRemove())
    except (httpx.RequestError, httpx.HTTPStatusError):
        await message.answer("😔 Не удалось сохранить номер.")

# --- FSM ---
@dp.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    if await state.get_state() is None: await message.answer("Нет активных действий для отмены."); return
    await state.clear(); await message.answer("Действие отменено.")

# Шаг 1
@dp.message(Command("book"))
async def start_booking(message: types.Message, state: FSMContext):
    await state.clear(); await state.set_state(AppointmentStates.choosing_service)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/services"); response.raise_for_status()
        services = response.json()
        builder = InlineKeyboardBuilder()
        for service in services: builder.button(text=f"{service['name']} ({service['price']} руб.)", callback_data=f"service_select:{service['id']}:{service['name']}:{service['price']}")
        builder.adjust(1)
        await message.answer("Выберите услугу:", reply_markup=builder.as_markup())
    except (httpx.RequestError, httpx.HTTPStatusError):
        await message.answer("😔 Не удалось загрузить список услуг."); await state.clear()

# Шаг 2
@dp.callback_query(AppointmentStates.choosing_service, F.data.startswith("service_select:"))
async def service_selected(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":", 3); service_id, service_name, service_price = int(parts[1]), parts[2], parts[3]
    await state.update_data(service_id=service_id, service_name=service_name, service_price=service_price)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/services/{service_id}/masters"); response.raise_for_status()
        masters = response.json()
        if not masters: await callback.message.edit_text("К сожалению, для этой услуги нет доступных мастеров."); await state.clear(); await callback.answer(); return
        builder = InlineKeyboardBuilder()
        if len(masters) > 1: builder.button(text="Любой свободный мастер", callback_data="master_select:any:Любой мастер")
        for master in masters: builder.button(text=master['name'], callback_data=f"master_select:{master['id']}:{master['name']}")
        builder.button(text="◀️ Назад", callback_data="back_to_service")
        builder.adjust(1)
        await callback.message.edit_text("Теперь выберите мастера:", reply_markup=builder.as_markup())
        await state.set_state(AppointmentStates.choosing_master)
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("😔 Не удалось загрузить список мастеров."); await state.clear()
    await callback.answer()

# Шаг 3
@dp.callback_query(AppointmentStates.choosing_master, F.data.startswith("master_select:"))
async def master_selected_show_calendar(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":", 2); master_id_str, master_name = parts[1], parts[2]
    master_id = None if master_id_str == 'any' else int(master_id_str)
    await state.update_data(master_id=master_id, master_name=master_name)
    today = date.today(); user_data = await state.get_data()
    try:
        params = {"service_id": user_data['service_id'], "year": today.year, "month": today.month}
        if master_id: params["master_id"] = master_id
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/active-days-in-month", params=params); response.raise_for_status()
        active_days = set(response.json())
    except: active_days = set()
    calendar_kb = create_calendar_keyboard(today.year, today.month, active_days)
    back_button = types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_master")
    calendar_kb.inline_keyboard.append([back_button])
    await callback.message.edit_text("Выберите дату:", reply_markup=calendar_kb)
    await state.set_state(AppointmentStates.choosing_date)
    await callback.answer()

# Шаг 4
@dp.callback_query(AppointmentStates.choosing_date, F.data.startswith("cal_day:"))
async def process_date_selected(callback: types.CallbackQuery, state: FSMContext):
    _, year, month, day = callback.data.split(":")
    selected_date = date(int(year), int(month), int(day))
    await state.update_data(selected_date=selected_date.isoformat())
    user_data = await state.get_data()
    params = {"service_id": user_data['service_id'], "selected_date": selected_date.isoformat()}
    if user_data.get('master_id'): params["master_id"] = user_data['master_id']
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/available-slots", params=params); response.raise_for_status()
        slots = response.json()
        if not slots: await callback.answer("На эту дату свободных слотов нет.", show_alert=True); return
        builder = InlineKeyboardBuilder()
        time_buttons = [types.InlineKeyboardButton(text=slot['time'], callback_data=f"time_select:{slot['time']}:{slot['master_id']}") for slot in slots]
        builder.add(*time_buttons)
        builder.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_date"))
        builder.adjust(4)
        await callback.message.edit_text("Выберите удобное время:", reply_markup=builder.as_markup())
        await state.set_state(AppointmentStates.choosing_time)
    except: await callback.message.edit_text("😔 Ошибка при поиске слотов."); await state.clear()
    await callback.answer()

# Шаг 5
@dp.callback_query(AppointmentStates.choosing_time, F.data.startswith("time_select:"))
async def time_selected(callback: types.CallbackQuery, state: FSMContext):
    try:
        parts = callback.data.split(':'); selected_time, selected_master_id = f"{parts[1]}:{parts[2]}", int(parts[3])
        await state.update_data(selected_time=selected_time, final_master_id=selected_master_id)
        user_data = await state.get_data()
        master_name_for_confirmation = user_data['master_name']
        if user_data.get('master_id') is None:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{API_URL}/api/v1/masters"); response.raise_for_status()
                all_masters = {master['id']: master['name'] for master in response.json()}
                master_name_for_confirmation = all_masters.get(selected_master_id, f"Мастер ID {selected_master_id}")
            except: master_name_for_confirmation = f"Мастер ID {selected_master_id}"
        confirmation_text = (f"Подтвердите запись:\n\n"
                             f"🔹 Услуга: {user_data['service_name']} ({user_data['service_price']} руб.)\n"
                             f"🔹 Мастер: {master_name_for_confirmation}\n"
                             f"📅 Дата: {user_data['selected_date']}\n"
                             f"🕒 Время: {selected_time}")
        builder = InlineKeyboardBuilder(); builder.button(text="✅ Подтвердить", callback_data="confirm_booking"); builder.button(text="◀️ Назад", callback_data="back_to_time")
        await callback.message.edit_text(confirmation_text, reply_markup=builder.as_markup())
        await state.set_state(AppointmentStates.confirmation)
    except Exception as e:
        logging.error(f"CRITICAL ERROR in [time_selected]: {e}", exc_info=True)
        await callback.answer("Произошла внутренняя ошибка.", show_alert=True); await state.clear()
    await callback.answer()

# Навигация по календарю
@dp.callback_query(AppointmentStates.choosing_date, F.data.startswith("cal_nav:"))
async def process_calendar_nav(callback: types.CallbackQuery, state: FSMContext):
    _, year_str, month_str = callback.data.split(":")
    year, month = int(year_str), int(month_str)
    user_data = await state.get_data()
    try:
        params = {"service_id": user_data['service_id'], "year": year, "month": month}
        if user_data.get('master_id'): params["master_id"] = user_data['master_id']
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/active-days-in-month", params=params); response.raise_for_status()
        active_days = set(response.json())
    except: active_days = set()
    calendar_kb = create_calendar_keyboard(year, month, active_days)
    back_button = types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_master")
    calendar_kb.inline_keyboard.append([back_button])
    await callback.message.edit_reply_markup(reply_markup=calendar_kb)
    await callback.answer()

# --- ОБРАБОТЧИКИ "НАЗАД" ---
@dp.callback_query(StateFilter(AppointmentStates.choosing_master), F.data == "back_to_service")
async def back_to_service(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AppointmentStates.choosing_service)
    # Повторяем логику start_booking, но с редактированием сообщения
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/services"); response.raise_for_status()
        services = response.json()
        builder = InlineKeyboardBuilder()
        for service in services: builder.button(text=f"{service['name']} ({service['price']} руб.)", callback_data=f"service_select:{service['id']}:{service['name']}:{service['price']}")
        builder.adjust(1)
        await callback.message.edit_text("Выберите услугу:", reply_markup=builder.as_markup())
    except:
        await callback.message.edit_text("😔 Не удалось загрузить услуги.")
        await state.clear()
    await callback.answer()

@dp.callback_query(StateFilter(AppointmentStates.choosing_date), F.data == "back_to_master")
async def back_to_master(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AppointmentStates.choosing_master)
    user_data = await state.get_data()
    service_id = user_data.get('service_id')
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/services/{service_id}/masters"); response.raise_for_status()
        masters = response.json()
        builder = InlineKeyboardBuilder()
        if len(masters) > 1: builder.button(text="Любой свободный мастер", callback_data="master_select:any:Любой мастер")
        for master in masters: builder.button(text=master['name'], callback_data=f"master_select:{master['id']}:{master['name']}")
        builder.button(text="◀️ Назад", callback_data="back_to_service")
        builder.adjust(1)
        await callback.message.edit_text("Теперь выберите мастера:", reply_markup=builder.as_markup())
    except:
        await callback.message.edit_text("😔 Не удалось загрузить мастеров.")
        await state.clear()
    await callback.answer()

@dp.callback_query(StateFilter(AppointmentStates.choosing_time), F.data == "back_to_date")
async def back_to_date(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AppointmentStates.choosing_date)
    await master_selected_show_calendar(callback, state)
    await callback.answer()

@dp.callback_query(StateFilter(AppointmentStates.confirmation), F.data == "back_to_time")
async def back_to_time(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AppointmentStates.choosing_time)
    user_data = await state.get_data()
    selected_date = date.fromisoformat(user_data['selected_date'])
    params = {"service_id": user_data['service_id'], "selected_date": selected_date.isoformat()}
    if user_data.get('master_id'): params["master_id"] = user_data['master_id']
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/available-slots", params=params); response.raise_for_status()
        slots = response.json()
        builder = InlineKeyboardBuilder()
        time_buttons = [types.InlineKeyboardButton(text=slot['time'], callback_data=f"time_select:{slot['time']}:{slot['master_id']}") for slot in slots]
        builder.add(*time_buttons)
        builder.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_date"))
        builder.adjust(4)
        await callback.message.edit_text("Выберите удобное время:", reply_markup=builder.as_markup())
    except: await callback.message.edit_text("😔 Ошибка при поиске слотов."); await state.clear()
    await callback.answer()

# --- Финал ---
@dp.callback_query(AppointmentStates.confirmation, F.data == "confirm_booking")
async def confirm_booking_handler(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    start_time_str = f"{user_data['selected_date']}T{user_data['selected_time']}:00"
    payload = {"telegram_user_id": callback.from_user.id, "user_name": callback.from_user.full_name, "service_id": user_data['service_id'], "master_id": user_data['final_master_id'], "start_time": start_time_str}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_URL}/api/v1/appointments", json=payload); response.raise_for_status()
        api_response = response.json()
        await callback.message.edit_text(
            f"🎉 Отлично! Вы успешно записаны!\n\n"
            f"Ждем вас {user_data['selected_date']} в {user_data['selected_time']} "
            f"на услугу '{api_response['service_name']}' к мастеру {api_response['master_name']}."
        )
        keyboard = types.ReplyKeyboardMarkup(keyboard=[[types.KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
        await callback.message.answer("Для удобства и быстрой связи, пожалуйста, поделитесь вашим номером телефона.", reply_markup=keyboard)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409: await callback.message.edit_text("😔 Ой, кто-то только что занял это время! Начните заново (/book).")
        else: await callback.message.edit_text("😔 Произошла ошибка при создании записи."); logging.error(f"API Error: {e.response.text}")
    except httpx.RequestError: await callback.message.edit_text("😔 Сервис записи временно недоступен.")
    await state.clear(); await callback.answer()

@dp.callback_query(StateFilter(AppointmentStates.confirmation), F.data == "cancel_booking")
async def cancel_booking_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear(); await callback.message.edit_text("Запись отменена."); await callback.answer()

# --- Запуск ---
async def main():
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Начало работы"),
        types.BotCommand(command="book", description="Записаться на услугу"),
        types.BotCommand(command="my_appointments", description="Мои записи"),
        types.BotCommand(command="cancel", description="Отменить действие"),
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
