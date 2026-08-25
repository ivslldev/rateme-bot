"""All FSM states used by the bot."""
from aiogram.fsm.state import State, StatesGroup


class ProfileStates(StatesGroup):
    """Profile creation wizard."""
    waiting_name = State()          # step 1: name (text)
    waiting_gender = State()        # step 2: own gender (inline)
    waiting_target_gender = State() # step 3: gender to rate (inline)
    waiting_photos = State()        # step 4: 1..3 photos


class MessageStates(StatesGroup):
    """Temporary user-to-user messaging."""
    waiting_message = State()       # capturing one text message to forward