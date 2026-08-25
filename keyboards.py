"""All inline keyboards and rating scales."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Rating scales (score -> label)
MALE_SCALE = {1: "Sub 3", 2: "Sub 5", 3: "Ltn", 4: "Mtn", 5: "Htn", 6: "Chad", 7: "True Adam"}
FEMALE_SCALE = {1: "Sub 3", 2: "Sub 5", 3: "Ltb", 4: "Mtb", 5: "Htb", 6: "Stacy", 7: "True Eve"}


def gender_kb() -> InlineKeyboardMarkup:
    """Step 2: own gender."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👨 Мужской", callback_data="gender:male"),
        InlineKeyboardButton(text="👩 Женский", callback_data="gender:female"),
    ]])


def target_gender_kb() -> InlineKeyboardMarkup:
    """Step 3: which gender the user wants to rate."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👨 Мужчины", callback_data="target:male"),
        InlineKeyboardButton(text="👩 Женщины", callback_data="target:female"),
    ]])


def photos_done_kb(count: int) -> InlineKeyboardMarkup:
    """Shown while collecting photos: allows finishing early with 1-2 photos."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"✅ Готово ({count}/3)", callback_data="photos:done"),
    ]])


def main_menu_kb(debug: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔥 Оценивать других", callback_data="act:rate")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="act:profile")],
        [InlineKeyboardButton(text="📖 Правила и шкалы", callback_data="act:help")],
    ]
    if debug:
        rows.append([InlineKeyboardButton(text="🧪 Тест-меню", callback_data="act:test")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def scale_kb(ratee_id: int, gender: str) -> InlineKeyboardMarkup:
    """Rating buttons 1..7 with scale labels; scale depends on ratee's gender."""
    scale = MALE_SCALE if gender == "male" else FEMALE_SCALE
    row1, row2 = [], []
    for score in range(1, 8):
        btn = InlineKeyboardButton(
            text=f"{score}·{scale[score]}",
            callback_data=f"rate:{ratee_id}:{score}",
        )
        (row1 if score <= 4 else row2).append(btn)
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])


def notification_kb(rater_id: int) -> InlineKeyboardMarkup:
    """Buttons under a rating notification."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔄 Оценить в ответ", callback_data=f"rateback:{rater_id}"),
        InlineKeyboardButton(text="🚩 Пожаловаться", callback_data=f"report:{rater_id}"),
        InlineKeyboardButton(text="✉️ Отправить сообщение", callback_data=f"msg:{rater_id}"),
    ]])


def test_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать 5 тестовых профилей", callback_data="test:create")],
        [InlineKeyboardButton(text="🔁 Переключить профиль", callback_data="test:switch")],
        [InlineKeyboardButton(text="🎲 Смоделировать оценку", callback_data="test:sim")],
        [InlineKeyboardButton(text="🚪 Выйти из тест-режима", callback_data="test:exit")],
    ])


def test_user_list_kb(users, prefix: str, extra: list = None) -> InlineKeyboardMarkup:
    """Generic list of test profiles as buttons."""
    rows = [[InlineKeyboardButton(
        text=f"{u['name']} ({'М' if u['gender'] == 'male' else 'Ж'})",
        callback_data=f"{prefix}:{u['telegram_id']}",
    )] for u in users]
    for btn in (extra or []):
        rows.append([btn])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="test:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sim_score_kb(rater_id: int, ratee_id: int) -> InlineKeyboardMarkup:
    """Score picker for rating simulation."""
    row1 = [InlineKeyboardButton(text=str(s), callback_data=f"tsrs:{rater_id}:{ratee_id}:{s}") for s in range(1, 5)]
    row2 = [InlineKeyboardButton(text=str(s), callback_data=f"tsrs:{rater_id}:{ratee_id}:{s}") for s in range(5, 8)]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2, [
        InlineKeyboardButton(text="⬅️ Назад", callback_data="test:sim"),
    ]])