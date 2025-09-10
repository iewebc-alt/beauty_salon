# keyboards.py - Этот файл будет содержать функции для генерации клавиатур, в данном случае — календаря.
import calendar
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

def create_calendar_keyboard(year: int, month: int, active_days: set = None) -> types.InlineKeyboardMarkup:
    if active_days is None:
        active_days = set()
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
            if day == 0:
                row_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
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
