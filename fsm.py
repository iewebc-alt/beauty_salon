# fsm.py - Здесь мы определим состояния для машины состояний (FSM).
from aiogram.fsm.state import State, StatesGroup

class AppointmentStates(StatesGroup):
    choosing_service = State()
    choosing_master = State()
    choosing_date = State()
    choosing_time = State()
    confirmation = State()
