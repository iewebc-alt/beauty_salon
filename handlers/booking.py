# handlers/booking.py
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
import httpx
import logging
import json

from fsm import AppointmentStates
from keyboards import create_calendar_keyboard
from services.api_client import api_client

router = Router()

# Шаг 1: /book
@router.message(Command("book"))
async def start_booking(message: types.Message, state: FSMContext, salon_token: str):
    await state.clear()
    await state.set_state(AppointmentStates.choosing_service)
    try:
        services = await api_client.get_services(token=salon_token)
        builder = InlineKeyboardBuilder()
        for service in services:
            builder.button(
                text=f"{service['name']} ({service['price']} руб.)",
                callback_data=f"service_select:{service['id']}",
            )
        builder.adjust(1)
        await message.answer(
            "Какую процедуру для вашей красоты выберем сегодня? ✨",
            reply_markup=builder.as_markup(),
        )
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logging.error(f"API Error: {e}")
        await message.answer(
            "Ой, не могу сейчас загрузить список наших прекрасных услуг. Попробуйте, пожалуйста, через минутку! 😔"
        )
        await state.clear()


# Шаг 2: Выбор услуги
@router.callback_query(
    AppointmentStates.choosing_service, F.data.startswith("service_select:")
)
async def service_selected(callback: types.CallbackQuery, state: FSMContext, salon_token: str):
    service_id = int(callback.data.split(":")[1])
    
    try:
        services = await api_client.get_services(token=salon_token)
        selected_service = next((s for s in services if s['id'] == service_id), None)
        
        if not selected_service:
            await callback.answer("Услуга не найдена", show_alert=True)
            return

        await state.update_data(
            service_id=service_id, 
            service_name=selected_service['name'], 
            service_price=selected_service['price']
        )
        
        masters = await api_client.get_masters_for_service(service_id, token=salon_token)
        
        if not masters:
            await callback.message.edit_text(
                f"К сожалению, на услугу «{selected_service['name']}» сейчас нет свободных мастеров. Может, выберете другую? 💖"
            )
            await state.clear()
            return
        
        builder = InlineKeyboardBuilder()
        if len(masters) > 1:
            builder.button(
                text="Любой свободный мастер",
                callback_data="master_select:any",
            )
        
        for master in masters:
            builder.button(
                text=master["name"],
                callback_data=f"master_select:{master['id']}",
            )
            
        builder.button(text="◀️ Назад к услугам", callback_data="back_to_service")
        builder.adjust(1)
        
        await callback.message.edit_text(
            f"Отличный выбор! ✨ Выбрана услуга: **{selected_service['name']}**.\nТеперь давайте подберем мастера:",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        await state.set_state(AppointmentStates.choosing_master)
        
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logging.error(f"API Error: {e}")
        await callback.message.edit_text(
            "Простите, не могу загрузить список мастеров. Попробуйте, пожалуйста, еще раз. 🙏"
        )
        await state.clear()
    finally:
        await callback.answer()


# Шаг 3: Выбор мастера
@router.callback_query(
    AppointmentStates.choosing_master, F.data.startswith("master_select:")
)
async def master_selected_show_calendar(
    callback: types.CallbackQuery, state: FSMContext, salon_token: str
):
    master_id_str = callback.data.split(":")[1]
    master_id = None if master_id_str == "any" else int(master_id_str)
    
    master_name = "Любой мастер"
    if master_id:
        try:
            masters = await api_client.get_all_masters(token=salon_token)
            found = next((m for m in masters if m['id'] == master_id), None)
            if found:
                master_name = found['name']
        except:
            pass

    await state.update_data(master_id=master_id, master_name=master_name)
    
    moscow_tz = ZoneInfo("Europe/Moscow")
    today = datetime.now(moscow_tz).date()
    
    user_data = await state.get_data()
    try:
        active_days = await api_client.get_active_days(
            user_data["service_id"], today.year, today.month, token=salon_token, master_id=user_data.get("master_id")
        )
        calendar_kb = create_calendar_keyboard(
            today.year, today.month, set(active_days)
        )
        back_button = types.InlineKeyboardButton(
            text="◀️ Назад к мастерам", callback_data="back_to_master"
        )
        calendar_kb.inline_keyboard.append([back_button])
        
        await callback.message.edit_text(
            f"Мастер: **{master_name}**.\nТеперь выберите удобную дату: 🗓️",
            reply_markup=calendar_kb,
            parse_mode="Markdown"
        )
        await state.set_state(AppointmentStates.choosing_date)
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text(
            "Произошла ошибка при загрузке календаря. Попробуйте снова."
        )
    finally:
        await callback.answer()


# Шаг 4: Выбор даты
@router.callback_query(AppointmentStates.choosing_date, F.data.startswith("cal_day:"))
async def process_date_selected(callback: types.CallbackQuery, state: FSMContext, salon_token: str):
    _, year, month, day = callback.data.split(":")
    selected_date = date(int(year), int(month), int(day))
    await state.update_data(selected_date=selected_date.isoformat())
    user_data = await state.get_data()
    
    try:
        slots = await api_client.get_available_slots(
            service_id=user_data["service_id"],
            selected_date=selected_date.isoformat(),
            token=salon_token,
            master_id=user_data.get("master_id"),
        )
        
        if not slots:
            await callback.answer(
                "На эту дату, к сожалению, уже всё расписано. Посмотрите, пожалуйста, другой денёк. 😔",
                show_alert=True,
            )
            return
            
        builder = InlineKeyboardBuilder()
        for slot in slots:
            builder.button(
                text=slot["time"],
                callback_data=f"time_select:{slot['time']}:{slot['master_id']}",
            )
            
        builder.adjust(4)
        builder.row(
            types.InlineKeyboardButton(
                text="◀️ Назад к датам", callback_data="back_to_date"
            )
        )
        
        await callback.message.edit_text(
            f"Дата: {selected_date.strftime('%d.%m.%Y')}.\nВыберите удобное время: 🕒",
            reply_markup=builder.as_markup(),
        )
        await state.set_state(AppointmentStates.choosing_time)
        
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text(
            "Ой, что-то пошло не так при поиске свободного времени. Давайте попробуем еще разок! 😥"
        )
        await state.clear()
    finally:
        await callback.answer()


# Шаг 5: Выбор времени и Подтверждение
@router.callback_query(
    AppointmentStates.choosing_time, F.data.startswith("time_select:")
)
async def time_selected(callback: types.CallbackQuery, state: FSMContext, salon_token: str):
    try:
        parts = callback.data.split(":")
        selected_time = f"{parts[1]}:{parts[2]}"
        selected_master_id = int(parts[3])
        
        await state.update_data(
            selected_time=selected_time, final_master_id=selected_master_id
        )
        user_data = await state.get_data()
        
        master_name = user_data.get("master_name")
        if user_data.get("master_id") is None or True:
            try:
                all_masters = await api_client.get_all_masters(token=salon_token)
                found = next((m for m in all_masters if m['id'] == selected_master_id), None)
                if found:
                    master_name = found['name']
            except:
                pass

        selected_date_obj = date.fromisoformat(user_data["selected_date"])
        formatted_date = selected_date_obj.strftime("%d.%m.%Y")

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
        
        await callback.message.edit_text(
            confirmation_text, reply_markup=builder.as_markup(), parse_mode="Markdown"
        )
        await state.set_state(AppointmentStates.confirmation)
        
    except Exception as e:
        logging.error(f"CRITICAL ERROR in [time_selected]: {e}", exc_info=True)
        await callback.answer(
            "Ой, произошла ошибка. Пожалуйста, начните сначала. /book 🙏",
            show_alert=True,
        )
        await state.clear()
    finally:
        await callback.answer()


# --- Финал ---
@router.callback_query(AppointmentStates.confirmation, F.data == "confirm_booking")
async def confirm_booking_handler(callback: types.CallbackQuery, state: FSMContext, salon_token: str):
    user_data = await state.get_data()

    # ИСПРАВЛЕНИЕ: Отправляем время "как есть", без конвертации в UTC
    start_time_str = f"{user_data['selected_date']}T{user_data['selected_time']}:00"

    payload = {
        "telegram_user_id": callback.from_user.id,
        "user_name": callback.from_user.full_name,
        "service_id": user_data["service_id"],
        "master_id": user_data["final_master_id"],
        "start_time": start_time_str,
    }
    try:
        api_response = await api_client.create_appointment(payload, token=salon_token)

        response_dt_naive = datetime.fromisoformat(api_response["start_time"])
        formatted_date = response_dt_naive.strftime("%d %B %Y")
        formatted_time = response_dt_naive.strftime("%H:%M")

        await callback.message.edit_text(
            f"🎉 Ура! Я вас записала! \n\n"
            f"Будем с нетерпением ждать вас в салоне «Элеганс» {formatted_date} в {formatted_time} "
            f"на процедуру «{api_response['service_name']}» к мастеру {api_response['master_name']}. 💖"
        )

        keyboard = types.ReplyKeyboardMarkup(
            keyboard=[
                [
                    types.KeyboardButton(
                        text="📱 Оставить контакт для связи", request_contact=True
                    )
                ]
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

        await callback.message.answer(
            "Если необходимо уточнить детали, Вы можете оставить контактный номер для администратора. 👇",
            reply_markup=keyboard,
        )
        await state.clear()

    except httpx.HTTPStatusError as e:
        # ИСПРАВЛЕНИЕ: Читаем ошибку и переводим на русский
        error_msg = "Произошла ошибка при записи."
        try:
            detail = e.response.json().get("detail", "")
            if "Time booked" in detail or "booked" in detail:
                error_msg = "😔 Это время уже занято. Кто-то успел записаться раньше!"
            else:
                error_msg = f"😔 Ошибка: {detail}"
        except:
            pass

        await callback.message.edit_text(
            f"{error_msg}\n\nПожалуйста, выберите другое время: /book"
        )
        logging.error(f"API Error: {e.response.text}")
        await state.clear()
    except httpx.RequestError:
        await callback.message.edit_text(
            "😔 Наш сервис записи временно прилег отдохнуть. Попробуйте, пожалуйста, через несколько минут!"
        )
        await state.clear()

    await callback.answer()


@router.callback_query(
    StateFilter(AppointmentStates.confirmation), F.data == "cancel_booking"
)
async def cancel_booking_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Запись отменена. Если передумаете, я всегда здесь, чтобы помочь! 😊 /book"
    )
    await callback.answer()
