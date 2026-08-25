"""Helper functions: identity resolution, onboarding, profile sending, notifications."""
import logging
import os

from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto

import config
import db
import keyboards as kb
from states import ProfileStates

log = logging.getLogger(__name__)

RULES_TEXT = (
    "Добро пожаловать в RateMe! Вот шкала оценок. Пожалуйста, будьте честны и уважительны. "
    "Помните: шкала от 1 до 7 (или используйте названия из шкал). "
    "Чтобы получать оценки, вам сначала нужно оценить других."
)


def resolve_identity(telegram_id: int) -> int:
    """DEBUG-only identity overlay: if admin has an active test session,
    all handlers operate on behalf of the selected fake profile
    (a safe alternative to swapping telegram_id inside the users table)."""
    if config.DEBUG_MODE:
        acting = db.get_session(telegram_id)
        if acting:
            return acting
    return telegram_id


def profile_complete(row) -> bool:
    if not row:
        return False
    return bool(row["name"] and row["gender"] and row["target_gender"]
                and len(db.get_photos(row["telegram_id"])) > 0)


def scale_label(gender: str, score: int) -> str:
    scale = kb.MALE_SCALE if gender == "male" else kb.FEMALE_SCALE
    return scale.get(score, "?")


def avg_text(telegram_id: int) -> str:
    row = db.get_user(telegram_id)
    if db.count_received(telegram_id) == 0:
        return "—"
    return f"{row['avg_rating']:.1f}/7"


async def send_scale_images(bot: Bot, chat_id: int) -> None:
    """Send the two reference scale images as one media group (local files)."""
    media = []
    for path in (config.SCALE_MALE_IMG, config.SCALE_FEMALE_IMG):
        if os.path.exists(path):
            media.append(InputMediaPhoto(media=FSInputFile(path)))
    if media:
        media[0].caption = "📊 Шкалы оценок: True Adam (мужская) и True Eve (женская)"
        await bot.send_media_group(chat_id=chat_id, media=media)
    else:
        await bot.send_message(chat_id, "(Файлы шкал не найдены в assets/ — см. текстовые шкалы ниже)")


async def send_onboarding(bot: Bot, chat_id: int) -> None:
    """Reference images media group + rules text, right after profile completion."""
    await send_scale_images(bot, chat_id)
    await bot.send_message(chat_id, RULES_TEXT)


async def send_profile(bot: Bot, chat_id: int, row, caption: str, reply_markup=None) -> None:
    """Send a profile as a media group (1-3 photos) with caption; text fallback."""
    photos = db.get_photos(row["telegram_id"])
    if photos:
        media = [InputMediaPhoto(media=fid) for fid in photos[:3]]
        media[0].caption = caption
        await bot.send_media_group(chat_id=chat_id, media=media, reply_markup=reply_markup)
    else:
        await bot.send_message(chat_id, caption, reply_markup=reply_markup)


async def show_main_menu(bot: Bot, chat_id: int, telegram_id: int) -> None:
    row = db.get_user(telegram_id)
    if row["is_rateable"]:
        status = "✅ Ваш профиль открыт для оценок"
    else:
        status = f"⏳ Чтобы получать оценки, оцените ещё профилей: {row['ratings_to_unlock']}"
    text = f"🏠 {row['name']}, главное меню\n{status}\n⭐ Ваш средний рейтинг: {avg_text(telegram_id)}"
    await bot.send_message(chat_id, text, reply_markup=kb.main_menu_kb(config.DEBUG_MODE))


async def send_profile_for_rating(bot: Bot, chat_id: int, target_row) -> None:
    """Profile media group + scale buttons attached to it."""
    caption = f"👤 {target_row['name']}\nОцените профиль:"
    await send_profile(bot, chat_id, target_row, caption,
                       reply_markup=kb.scale_kb(target_row["telegram_id"], target_row["gender"]))


async def show_next_profile(bot: Bot, chat_id: int, rater_id: int) -> bool:
    """Find and show the next rateable profile of the rater's target gender."""
    rater = db.get_user(rater_id)
    nxt = db.get_next_rateable(rater_id, rater["target_gender"])
    if not nxt:
        await bot.send_message(chat_id, "😔 Пока нет доступных профилей для оценки. Загляните позже!")
        return False
    await send_profile_for_rating(bot, chat_id, nxt)
    return True


async def notify_ratee(bot: Bot, rater_row, ratee_row, score: int) -> None:
    """Send rating notification to the ratee: rater's profile + score + action buttons."""
    try:
        caption = (f"👤 {rater_row['name']}\n"
                   f"⭐ Средний: {avg_text(rater_row['telegram_id'])}")
        await send_profile(bot, ratee_row["telegram_id"], rater_row, caption)
        label = scale_label(ratee_row["gender"], score)
        text = (f"🔔 Новая оценка! Пользователь оценил ваш профиль.\n"
                f"Поставил вам: {score} ({label})")
        await bot.send_message(ratee_row["telegram_id"], text,
                               reply_markup=kb.notification_kb(rater_row["telegram_id"]))
    except Exception as exc:  # ratee may be a fake/unreachable chat
        log.warning("Cannot notify ratee %s: %s", ratee_row["telegram_id"], exc)


async def process_rating(bot: Bot, rater_id: int, ratee_id: int, score: int) -> bool:
    """Central rating routine shared by the real flow and the test simulator."""
    if rater_id == ratee_id:
        return False
    added = db.add_rating(rater_id, ratee_id, score)
    if added:
        rater_row, ratee_row = db.get_user(rater_id), db.get_user(ratee_id)
        if rater_row and ratee_row:
            await notify_ratee(bot, rater_row, ratee_row, score)
    return added


async def run_start(bot: Bot, chat_id: int, telegram_id: int, state) -> None:
    """Resume/start the profile wizard at the correct step."""
    db.create_user(telegram_id)
    row = db.get_user(telegram_id)
    if not row["name"]:
        await state.set_state(ProfileStates.waiting_name)
        await bot.send_message(chat_id, "👋 Шаг 1/4: Как вас зовут?")
    elif not row["gender"]:
        await state.set_state(ProfileStates.waiting_gender)
        await bot.send_message(chat_id, "👋 Шаг 2/4: Ваш пол?", reply_markup=kb.gender_kb())
    elif not row["target_gender"]:
        await state.set_state(ProfileStates.waiting_target_gender)
        await bot.send_message(chat_id, "👋 Шаг 3/4: Кого вы хотите оценивать?",
                               reply_markup=kb.target_gender_kb())
    elif not db.get_photos(telegram_id):
        await state.set_state(ProfileStates.waiting_photos)
        await bot.send_message(chat_id, "👋 Шаг 4/4: Пришлите от 1 до 3 фото.",
                               reply_markup=kb.photos_done_kb(0))
    else:
        await show_main_menu(bot, chat_id, telegram_id)