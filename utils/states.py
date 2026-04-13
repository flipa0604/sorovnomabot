from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    wait_subscription = State()
    wait_instagram = State()
    wait_phone = State()


class Voting(StatesGroup):
    """Telefon tasdiqlandi — inline qidiruv va ovoz."""
    active = State()
