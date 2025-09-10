import asyncio
import logging
import httpx
import calendar
from datetime import datetime, date
import os
import locale

# --- ИМПОРТ GEMINI ---
import google.generativeai as genai

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- ИМПОРТИРУЕМ КЛЮЧИ ИЗ ФАЙЛА CONFIG.PY ---
try:
    from config import BOT_TOKEN, API_URL, GEMINI_API_KEY
except ImportError:
    logging.critical("Не удалось импортировать ключи из файла config.py! Убедитесь, что файл существует и содержит BOT_TOKEN, API_URL и GEMINI_API_KEY.")
    exit("Config file not found or incomplete!")


# --- Настройка логгирования ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

# --- Инициализация бота ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Настройка Gemini ---
gemini_model = None
# Проверяем, был ли ключ загружен из .env
if not GEMINI_API_KEY:
    logging.warning("Ключ API для Gemini (GEMINI_API_KEY) не найден в .env! Ответы на отвлеченные темы будут стандартными.")
else:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # --- ИЗМЕНЕНИЕ ЗДЕСЬ: используем более стабильное имя модели ---
        #gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')
        gemini_model = genai.GenerativeModel('ggemini-2.5-flash')
        logging.info("Модель Gemini успешно инициализирована.")
    except Exception as e:
        logging.error(f"Не удалось инициализировать Gemini: {e}")
        gemini_model = None


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
    month_names_ru = [
        "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    month_name = month_names_ru[month]
    builder.row(types.InlineKeyboardButton(text=f"{month_name} {year}", callback_data="ignore"))
    days_of_week = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    builder.row(*[types.InlineKeyboardButton(text=day, callback_data="ignore") for day in days_of_week])
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row_buttons = []
        for day in week:
            if day == 0: row_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
            elif day in active_days:
                row_buttons.append(types.InlineKeyboardButton(text=f"✅{day}", callback_data=f"cal_day:{year}:{month}:{day}"))
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
async def ignore_callback_handler(callback: types.CallbackQuery):
    await callback.answer("Ой, на этот день уже всё занято, выберите, пожалуйста, другой 😔", show_alert=True)

# --- Команды ---
@dp.message(CommandStart())
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

@dp.message(Command("my_appointments"))
async def show_my_appointments(message: types.Message):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/clients/{message.from_user.id}/appointments")
            response.raise_for_status()
        appointments = response.json()
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

@dp.callback_query(F.data.startswith("cancel_appt:"))
async def cancel_appointment_handler(callback: types.CallbackQuery):
    appointment_id = int(callback.data.split(":")[1])
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(f"{API_URL}/api/v1/appointments/{appointment_id}")
            response.raise_for_status()
        await callback.message.edit_text("Готово! Ваша запись отменена. Будем ждать вас в «Элеганс» в другой раз! 💖")
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("Что-то пошло не так, и не получилось отменить запись. Пожалуйста, попробуйте еще раз или свяжитесь с нами напрямую. 😥")
    await callback.answer()

@dp.message(F.contact)
async def handle_contact(message: types.Message):
    try:
        payload = {"phone_number": message.contact.phone_number}
        async with httpx.AsyncClient() as client:
            response = await client.patch(f"{API_URL}/api/v1/clients/{message.from_user.id}", json=payload)
            response.raise_for_status()
        await message.answer("Спасибо! Сохранила ваш номер телефона. Теперь мы сможем с вами связаться, если что-то изменится. 😊", reply_markup=types.ReplyKeyboardRemove())
    except (httpx.RequestError, httpx.HTTPStatusError):
        await message.answer("Простите, не удалось сохранить ваш номер телефона из-за технической ошибки. Попробуйте, пожалуйста, еще раз. 🙏")

# --- FSM Процесс записи ---
@dp.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Сейчас нет активного процесса записи, который можно было бы отменить. 😊")
        return
    await state.clear()
    await message.answer("Хорошо, я всё отменила. Давайте начнем заново, если хотите! /book")

# Шаг 1
@dp.message(Command("book"))
async def start_booking(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(AppointmentStates.choosing_service)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/services")
            response.raise_for_status()
        services = response.json()
        builder = InlineKeyboardBuilder()
        for service in services:
            builder.button(text=f"{service['name']} ({service['price']} руб.)", callback_data=f"service_select:{service['id']}:{service['name']}:{service['price']}")
        builder.adjust(1)
        await message.answer("Какую процедуру для вашей красоты выберем сегодня? ✨", reply_markup=builder.as_markup())
    except (httpx.RequestError, httpx.HTTPStatusError):
        await message.answer("Ой, не могу сейчас загрузить список наших прекрасных услуг. Попробуйте, пожалуйста, через минутку! 😔")
        await state.clear()

# Шаг 2
@dp.callback_query(AppointmentStates.choosing_service, F.data.startswith("service_select:"))
async def service_selected(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":", 3)
    service_id, service_name, service_price = int(parts[1]), parts[2], parts[3]
    await state.update_data(service_id=service_id, service_name=service_name, service_price=service_price)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/services/{service_id}/masters")
            response.raise_for_status()
        masters = response.json()
        if not masters:
            await callback.message.edit_text("К сожалению, на эту услугу сейчас нет свободных мастеров. Может, выберете другую? 💖")
            await state.clear()
            await callback.answer()
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
    await callback.answer()

# Шаг 3
@dp.callback_query(AppointmentStates.choosing_master, F.data.startswith("master_select:"))
async def master_selected_show_calendar(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":", 2)
    master_id_str, master_name = parts[1], parts[2]
    master_id = None if master_id_str == 'any' else int(master_id_str)
    await state.update_data(master_id=master_id, master_name=master_name)
    today = date.today()
    user_data = await state.get_data()
    try:
        params = {"service_id": user_data['service_id'], "year": today.year, "month": today.month}
        if master_id:
            params["master_id"] = master_id
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/active-days-in-month", params=params)
            response.raise_for_status()
        active_days = set(response.json())
    except:
        active_days = set()
    calendar_kb = create_calendar_keyboard(today.year, today.month, active_days)
    back_button = types.InlineKeyboardButton(text="◀️ Назад к мастерам", callback_data="back_to_master")
    calendar_kb.inline_keyboard.append([back_button])
    await callback.message.edit_text("Прекрасно! Теперь выберите удобную для вас дату в календаре: 🗓️", reply_markup=calendar_kb)
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
    if user_data.get('master_id'):
        params["master_id"] = user_data['master_id']
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/available-slots", params=params)
            response.raise_for_status()
        slots = response.json()
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
    except:
        await callback.message.edit_text("Ой, что-то пошло не так при поиске свободного времени. Давайте попробуем еще разок! 😥")
        await state.clear()
    await callback.answer()

# Шаг 5
@dp.callback_query(AppointmentStates.choosing_time, F.data.startswith("time_select:"))
async def time_selected(callback: types.CallbackQuery, state: FSMContext):
    try:
        parts = callback.data.split(':')
        selected_time, selected_master_id = f"{parts[1]}:{parts[2]}", int(parts[3])
        await state.update_data(selected_time=selected_time, final_master_id=selected_master_id)
        user_data = await state.get_data()
        master_name_for_confirmation = user_data['master_name']
        if user_data.get('master_id') is None:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{API_URL}/api/v1/masters")
                    response.raise_for_status()
                all_masters = {master['id']: master['name'] for master in response.json()}
                master_name_for_confirmation = all_masters.get(selected_master_id, f"Мастер ID {selected_master_id}")
            except:
                master_name_for_confirmation = f"Мастер ID {selected_master_id}"
        
        selected_date_obj = date.fromisoformat(user_data['selected_date'])
        formatted_date = selected_date_obj.strftime("%d %B %Y")

        confirmation_text = (
            f"Почти готово! Давайте всё проверим: 🥰\n\n"
            f"✨ **Услуга:** {user_data['service_name']} ({user_data['service_price']} руб.)\n"
            f"👩‍⚕️ **Мастер:** {master_name_for_confirmation}\n"
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
        await callback.answer("Ой, произошла какая-то внутренняя ошибка. Простите за неудобства! Пожалуйста, попробуйте начать сначала. /book 🙏", show_alert=True)
        await state.clear()
    await callback.answer()

# Навигация по календарю
@dp.callback_query(AppointmentStates.choosing_date, F.data.startswith("cal_nav:"))
async def process_calendar_nav(callback: types.CallbackQuery, state: FSMContext):
    _, year_str, month_str = callback.data.split(":")
    year, month = int(year_str), int(month_str)
    user_data = await state.get_data()
    try:
        params = {"service_id": user_data['service_id'], "year": year, "month": month}
        if user_data.get('master_id'):
            params["master_id"] = user_data['master_id']
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/active-days-in-month", params=params)
            response.raise_for_status()
        active_days = set(response.json())
    except:
        active_days = set()
    calendar_kb = create_calendar_keyboard(year, month, active_days)
    back_button = types.InlineKeyboardButton(text="◀️ Назад к мастерам", callback_data="back_to_master")
    calendar_kb.inline_keyboard.append([back_button])
    await callback.message.edit_reply_markup(reply_markup=calendar_kb)
    await callback.answer()

# --- ОБРАБОТЧИКИ "НАЗАД" ---
@dp.callback_query(StateFilter(AppointmentStates.choosing_master), F.data == "back_to_service")
async def back_to_service(callback: types.CallbackQuery, state: FSMContext):
    # Используем message из callback, чтобы отправить новое сообщение, а не редактировать
    await start_booking(callback.message, state)
    await callback.answer() # Закрываем "часики" на кнопке

@dp.callback_query(StateFilter(AppointmentStates.choosing_date), F.data == "back_to_master")
async def back_to_master(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AppointmentStates.choosing_master)
    user_data = await state.get_data()
    service_id = user_data.get('service_id')
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/services/{service_id}/masters")
            response.raise_for_status()
        masters = response.json()
        builder = InlineKeyboardBuilder()
        if len(masters) > 1:
            builder.button(text="Любой свободный мастер", callback_data="master_select:any:Любой мастер")
        for master in masters:
            builder.button(text=master['name'], callback_data=f"master_select:{master['id']}:{master['name']}")
        builder.button(text="◀️ Назад к услугам", callback_data="back_to_service")
        builder.adjust(1)
        await callback.message.edit_text("Хорошо, давайте выберем другого мастера:", reply_markup=builder.as_markup())
    except:
        await callback.message.edit_text("Простите, не могу загрузить список мастеров. Попробуйте, пожалуйста, еще раз. 🙏")
        await state.clear()
    await callback.answer()

@dp.callback_query(StateFilter(AppointmentStates.choosing_time), F.data == "back_to_date")
async def back_to_date(callback: types.CallbackQuery, state: FSMContext):
    # --- НАЧАЛО ИСПРАВЛЕННОГО БЛОКА ---
    await state.set_state(AppointmentStates.choosing_date)
    user_data = await state.get_data()

    # Восстанавливаем год и месяц из сохраненной даты
    selected_date = date.fromisoformat(user_data['selected_date'])
    year, month = selected_date.year, selected_date.month

    try:
        params = {"service_id": user_data['service_id'], "year": year, "month": month}
        if user_data.get('master_id'):
            params["master_id"] = user_data['master_id']
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/active-days-in-month", params=params)
            response.raise_for_status()
        active_days = set(response.json())
    except:
        active_days = set()

    # Генерируем календарь для нужного месяца
    calendar_kb = create_calendar_keyboard(year, month, active_days)
    back_button = types.InlineKeyboardButton(text="◀️ Назад к мастерам", callback_data="back_to_master")
    calendar_kb.inline_keyboard.append([back_button])
    
    await callback.message.edit_text("Хорошо, давайте выберем другую дату: 🗓️", reply_markup=calendar_kb)
    await callback.answer()
    # --- КОНЕЦ ИСПРАВЛЕННОГО БЛОКА ---

@dp.callback_query(StateFilter(AppointmentStates.confirmation), F.data == "back_to_time")
async def back_to_time(callback: types.CallbackQuery, state: FSMContext):
    # --- НАЧАЛО ИСПРАВЛЕННОГО БЛОКА ---
    await state.set_state(AppointmentStates.choosing_time)
    user_data = await state.get_data()
    
    # Мы уже знаем дату, она сохранена в state. Просто запрашиваем слоты для неё.
    params = {
        "service_id": user_data['service_id'], 
        "selected_date": user_data['selected_date']
    }
    if user_data.get('master_id'):
        params["master_id"] = user_data['master_id']

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/api/v1/available-slots", params=params)
            response.raise_for_status()
        slots = response.json()
        
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
    # --- КОНЕЦ ИСПРАВЛЕННОГО БЛОКА ---

# --- Финал ---
@dp.callback_query(AppointmentStates.confirmation, F.data == "confirm_booking")
async def confirm_booking_handler(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    start_time_str = f"{user_data['selected_date']}T{user_data['selected_time']}:00"
    payload = {
        "telegram_user_id": callback.from_user.id,
        "user_name": callback.from_user.full_name,
        "service_id": user_data['service_id'],
        "master_id": user_data['final_master_id'],
        "start_time": start_time_str
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_URL}/api/v1/appointments", json=payload)
            response.raise_for_status()
        api_response = response.json()
        
        selected_date_obj = date.fromisoformat(user_data['selected_date'])
        formatted_date = selected_date_obj.strftime("%d %B %Y")

        await callback.message.edit_text(
            f"🎉 Ура! Я вас записала! \n\n"
            f"Будем с нетерпением ждать вас в салоне «Элеганс» {formatted_date} в {user_data['selected_time']} "
            f"на процедуру «{api_response['service_name']}» к мастеру {api_response['master_name']}. 💖"
        )
        
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
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
    await state.clear()
    await callback.answer()


@dp.callback_query(StateFilter(AppointmentStates.confirmation), F.data == "cancel_booking")
async def cancel_booking_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Запись отменена. Если передумаете, я всегда здесь, чтобы помочь! 😊 /book")
    await callback.answer()


# --- НОВАЯ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ---
async def resend_current_state_message(message: types.Message, state: FSMContext):
    """
    Повторно отправляет сообщение с кнопками, соответствующее текущему состоянию FSM.
    """
    current_state_str = await state.get_state()
    user_data = await state.get_data()
    
    # Создаем "фейковый" callback, чтобы переиспользовать существующие функции
    # Это проще, чем дублировать код
    class FakeCallback:
        def __init__(self, msg):
            self.message = msg
        async def answer(self):
            pass
    
    fake_callback = FakeCallback(message)

    if current_state_str == AppointmentStates.choosing_service.state:
        await start_booking(message, state)
    elif current_state_str == AppointmentStates.choosing_master.state:
        await service_selected(fake_callback, state)
    elif current_state_str == AppointmentStates.choosing_date.state:
        await master_selected_show_calendar(fake_callback, state)
    elif current_state_str == AppointmentStates.choosing_time.state:
        await process_date_selected(fake_callback, state)
    elif current_state_str == AppointmentStates.confirmation.state:
        await time_selected(fake_callback, state)


# --- ОБРАБОТЧИКИ НЕПРЕДВИДЕННОГО ВВОДА ---
@dp.message(F.text, StateFilter(AppointmentStates))
async def handle_text_while_in_state(message: types.Message, state: FSMContext):
    if gemini_model:
        try:
            await bot.send_chat_action(message.chat.id, 'typing')
            prompt = (
                "Ты — Gemini, работающий в режиме милой и дружелюбной девушки-администратора в бьюти-мед салоне 'Элеганс'. "
                "Клиент находится в процессе записи на услугу (он видит перед собой кнопки для выбора), но вместо нажатия на кнопку написал отвлеченное сообщение. "
                "Твоя задача — вежливо и креативно отреагировать на его сообщение, но сразу же мягко вернуть его к процессу записи. "
                "Ты должна напомнить, что ему нужно использовать кнопки, или он может отменить запись командой /cancel. "
                "Твой ответ должен быть коротким, позитивным, без Markdown. В конце обязательно упомяни команду /cancel. "
                f'Вот сообщение клиента: "{message.text}"'
            )
            response = await gemini_model.generate_content_async(prompt)
            await message.answer(response.text)
        except Exception as e:
            logging.error(f"Ошибка при обращении к Gemini API во время FSM: {e}")
            await message.answer("Ой, кажется, мы немного отвлеклись! 😊 Давайте вернемся к выбору.")
            await resend_current_state_message(message, state)
    else:
        await message.answer("Ой, кажется, мы немного отвлеклись! 😊")
        await resend_current_state_message(message, state)


# Ловит ЛЮБОЙ контент, когда пользователь НЕ в процессе записи
@dp.message(StateFilter(None))
async def handle_unhandled_content(message: types.Message):
    if gemini_model and message.text:
        try:
            await bot.send_chat_action(message.chat.id, 'typing')
            prompt = (
                "Ты — Gemini, работающий в режиме милой и дружелюбной девушки-администратора в бьюти-мед салоне 'Элеганс'. "
                "Клиент написал тебе сообщение, не связанное напрямую с записью на услуги. "
                "Твоя задача — вежливо и мило ответить, извиниться, что не можешь поддержать разговор на любую тему, и мягко направить его к основным функциям бота: записи на услугу или просмотру существующих записей. "
                "Твой ответ должен быть коротким (2-3 предложения), очень вежливым и позитивным. Не используй Markdown. В конце обязательно предложи основные команды `/book` и `/my_appointments` в формате новой строки. "
                f'Вот сообщение клиента: "{message.text}"'
            )
            response = await gemini_model.generate_content_async(prompt)
            await message.answer(response.text)
        except Exception as e:
            logging.error(f"Ошибка при обращении к Gemini API: {e}")
            await message.answer(
                "Простите, у меня небольшая техническая заминка! 😥 Давайте вернемся к главному. Могу я вам помочь с записью?\n\n"
                "✨ /book - Записаться\n"
                "🗓️ /my_appointments - Мои записи"
            )
    else:
        await message.answer(
            "Какой милый стикер! 😊 Простите, я лучше всего умею записывать на наши прекрасные процедуры. Могу я вам с этим помочь?\n\n"
            "✨ /book - Записаться\n"
            "🗓️ /my_appointments - Мои записи"
        )

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
    try:
        locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    except locale.Error:
        logging.warning("Локаль ru_RU.UTF-8 не найдена, месяцы могут отображаться на английском.")
    asyncio.run(main())
