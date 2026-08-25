"""All handlers: profile wizard, main menu, rating flow, messaging, test toolbox."""
import logging
import os
import random

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           FSInputFile, Message)

import config
import db
import keyboards as kb
import utils as ut
from states import MessageStates, ProfileStates

router = Router()
log = logging.getLogger(__name__)

TEST_PROFILES = [("Анна", "female"), ("Мария", "female"), ("Иван", "male"),
                 ("Алексей", "male"), ("Катя", "female")]
DONE_WORDS = {"готово", "done", "finish", "завершить", "/done", "✅"}


# ================= /start & commands =================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    tg_id = ut.resolve_identity(message.from_user.id)
    row = db.get_user(tg_id)
    if row and ut.profile_complete(row):
        await ut.show_main_menu(message.bot, message.chat.id, tg_id)
    else:
        await ut.run_start(message.bot, message.chat.id, tg_id, state)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    tg_id = ut.resolve_identity(message.from_user.id)
    if ut.profile_complete(db.get_user(tg_id)):
        await ut.show_main_menu(message.bot, message.chat.id, tg_id)
    else:
        await ut.run_start(message.bot, message.chat.id, tg_id, state)


# ================= Profile wizard (FSM) =================

@router.message(ProfileStates.waiting_name, F.text)
async def on_name(message: Message, state: FSMContext):
    tg_id = ut.resolve_identity(message.from_user.id)
    db.create_user(tg_id)
    db.set_name(tg_id, message.text.strip()[:50])
    await state.set_state(ProfileStates.waiting_gender)
    await message.answer("👤 Шаг 2/4: Ваш пол?", reply_markup=kb.gender_kb())


@router.callback_query(ProfileStates.waiting_gender, F.data.startswith("gender:"))
async def on_gender(callback: CallbackQuery, state: FSMContext):
    tg_id = ut.resolve_identity(callback.from_user.id)
    db.set_gender(tg_id, callback.data.split(":")[1])
    await state.set_state(ProfileStates.waiting_target_gender)
    await callback.message.edit_text("🎯 Шаг 3/4: Кого вы хотите оценивать?",
                                     reply_markup=kb.target_gender_kb())
    await callback.answer()


@router.callback_query(ProfileStates.waiting_target_gender, F.data.startswith("target:"))
async def on_target(callback: CallbackQuery, state: FSMContext):
    tg_id = ut.resolve_identity(callback.from_user.id)
    db.set_target_gender(tg_id, callback.data.split(":")[1])
    await state.set_state(ProfileStates.waiting_photos)
    await callback.message.edit_text(
        "📸 Шаг 4/4: Пришлите от 1 до 3 фотографий (по одной или альбомом). "
        "После 3-й фото этап завершится автоматически.",
        reply_markup=kb.photos_done_kb(0))
    await callback.answer()


@router.message(ProfileStates.waiting_photos, F.photo)
async def on_photo(message: Message, state: FSMContext):
    tg_id = ut.resolve_identity(message.from_user.id)
    data = await state.get_data()
    count = int(data.get("photo_count", 0))
    db.add_photo(tg_id, message.photo[-1].file_id)  # store Telegram file_id
    count += 1
    if count >= 3:  # auto-finish after the 3rd photo
        await state.clear()
        await ut.send_onboarding(message.bot, message.chat.id)
        await ut.show_main_menu(message.bot, message.chat.id, tg_id)
    else:
        await state.update_data(photo_count=count)
        await message.answer(f"📸 Получено фото {count}/3. Отправьте ещё или завершите.",
                             reply_markup=kb.photos_done_kb(count))


@router.message(ProfileStates.waiting_photos, F.text)
async def on_photo_text(message: Message, state: FSMContext):
    """Text input during photo step: 'done' finishes early, anything else re-prompts."""
    tg_id = ut.resolve_identity(message.from_user.id)
    data = await state.get_data()
    count = int(data.get("photo_count", 0))
    if message.text.strip().lower() in DONE_WORDS:
        if count >= 1:
            await state.clear()
            await ut.send_onboarding(message.bot, message.chat.id)
            await ut.show_main_menu(message.bot, message.chat.id, tg_id)
        else:
            await message.answer("Нужно хотя бы одно фото 🙏")
    else:
        await message.answer("Пожалуйста, отправьте фото (или напишите «готово»).",
                             reply_markup=kb.photos_done_kb(count))


@router.callback_query(ProfileStates.waiting_photos, F.data == "photos:done")
async def on_photos_done(callback: CallbackQuery, state: FSMContext):
    tg_id = ut.resolve_identity(callback.from_user.id)
    count = len(db.get_photos(tg_id))
    if count >= 1:
        await state.clear()
        await callback.answer()
        await ut.send_onboarding(callback.bot, callback.message.chat.id)
        await ut.show_main_menu(callback.bot, callback.message.chat.id, tg_id)
    else:
        await callback.answer("Нужно хотя бы одно фото", show_alert=True)


# ================= Main menu actions =================

@router.callback_query(F.data == "act:rate")
async def on_act_rate(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    tg_id = ut.resolve_identity(callback.from_user.id)
    await callback.answer()
    await ut.show_next_profile(callback.bot, callback.message.chat.id, tg_id)


@router.callback_query(F.data == "act:profile")
async def on_act_profile(callback: CallbackQuery):
    tg_id = ut.resolve_identity(callback.from_user.id)
    row = db.get_user(tg_id)
    received = db.count_received(tg_id)
    caption = (f"👤 Ваш профиль: {row['name']}\n"
               f"⭐ Средний: {ut.avg_text(tg_id)} (оценок: {received})\n"
               f"🔓 Осталось оценить до разблокировки: {row['ratings_to_unlock']}"
               if not row["is_rateable"] else
               f"👤 Ваш профиль: {row['name']}\n⭐ Средний: {ut.avg_text(tg_id)} (оценок: {received})\n🔓 Профиль открыт для оценок")
    await ut.send_profile(callback.bot, callback.message.chat.id, row, caption)
    await callback.answer()


@router.callback_query(F.data == "act:help")
async def on_act_help(callback: CallbackQuery):
    await callback.answer()
    await ut.send_onboarding(callback.bot, callback.message.chat.id)


@router.callback_query(F.data == "act:test")
async def on_act_test(callback: CallbackQuery):
    await show_test_menu(callback)


# ================= Rating flow =================

@router.callback_query(F.data.startswith("rate:"))
async def on_rate(callback: CallbackQuery):
    _, ratee_s, score_s = callback.data.split(":")
    ratee_id, score = int(ratee_s), int(score_s)
    rater_id = ut.resolve_identity(callback.from_user.id)

    if rater_id == ratee_id:
        return await callback.answer("Нельзя оценить себя", show_alert=True)
    if db.has_rated(rater_id, ratee_id):
        return await callback.answer("Вы уже оценили этот профиль", show_alert=True)

    db.add_rating(rater_id, ratee_id, score)
    ratee_row = db.get_user(ratee_id)
    label = ut.scale_label(ratee_row["gender"], score)
    await callback.answer("✅ Оценка сохранена!")

    # Disable old keyboard on the profile message
    try:
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=f"✅ Оценено: {score} ({label})",
                                                   callback_data="noop")]]))
    except Exception:
        pass

    # Notify the ratee (instant inline notification)
    rater_row = db.get_user(rater_id)
    if rater_row and ratee_row:
        await ut.notify_ratee(callback.bot, rater_row, ratee_row, score)

    # Show the next profile right away
    await ut.show_next_profile(callback.bot, callback.message.chat.id, rater_id)


@router.callback_query(F.data.startswith("rateback:"))
async def on_rateback(callback: CallbackQuery):
    """'Rate back' from a notification: show that exact profile with scale buttons."""
    target_id = int(callback.data.split(":")[1])
    me_id = ut.resolve_identity(callback.from_user.id)
    target = db.get_user(target_id)
    if not target:
        return await callback.answer("Профиль не найден", show_alert=True)
    if db.has_rated(me_id, target_id):
        return await callback.answer("Вы уже оценили этого пользователя", show_alert=True)
    await callback.answer()
    await ut.send_profile_for_rating(callback.bot, callback.message.chat.id, target)


@router.callback_query(F.data.startswith("report:"))
async def on_report(callback: CallbackQuery):
    target_id = int(callback.data.split(":")[1])
    total = db.increment_reports(target_id)
    await callback.answer("🚩 Жалоба отправлена. Спасибо!", show_alert=True)
    if config.ADMIN_ID:  # signal the admin if configured
        row = db.get_user(target_id)
        try:
            await callback.bot.send_message(
                config.ADMIN_ID,
                f"🚩 Жалоба на {row['name']} (id={target_id}). Всего жалоб: {total}")
        except Exception as exc:
            log.warning("Cannot notify admin: %s", exc)


@router.callback_query(F.data == "noop")
async def on_noop(callback: CallbackQuery):
    await callback.answer()


# ================= User-to-user messaging =================
# Simplified approach allowed by the spec: counterpart id travels in callback data,
# the FSM stores the target; the `exchanges` table enforces the one-message limit.

@router.callback_query(F.data.startswith("msg:"))
async def on_msg(callback: CallbackQuery, state: FSMContext):
    target_id = int(callback.data.split(":")[1])
    me_id = ut.resolve_identity(callback.from_user.id)
    if db.exchange_exists(me_id, target_id):
        return await callback.answer("⏳ Вы уже отправили сообщение. Дождитесь ответа.",
                                     show_alert=True)
    await state.set_state(MessageStates.waiting_message)
    await state.update_data(target=target_id)
    await callback.answer()
    await callback.message.answer("✉️ Напишите одно сообщение — я перешлю его собеседнику.")


@router.message(MessageStates.waiting_message)
async def on_message_send(message: Message, state: FSMContext):
    data = await state.get_data()
    target_id = int(data["target"])
    me_id = ut.resolve_identity(message.from_user.id)
    await state.clear()

    if db.exchange_exists(me_id, target_id):
        return await message.answer("⏳ Сообщение уже отправлено, дождитесь ответа.")

    # If the counterpart wrote first, this text counts as the reply -> close exchange.
    if db.exchange_exists(target_id, me_id):
        db.exchange_delete(target_id, me_id)
    else:
        db.exchange_start(me_id, target_id)

    me_row, target_row = db.get_user(me_id), db.get_user(target_id)
    text = message.text or message.caption or "(без текста)"
    try:
        await message.bot.send_message(
            target_id,
            f"📩 Сообщение от {me_row['name']}:\n\n{text}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✉️ Ответить", callback_data=f"msg:{me_id}")]]))
        await message.answer("✅ Сообщение доставлено!")
    except Exception as exc:  # fake/unreachable user
        log.warning("Cannot forward message to %s: %s", target_id, exc)
        await message.answer("😔 Не удалось доставить сообщение.")


# ================= Admin test toolbox (/test_profiles) =================

def _admin_only(callback: CallbackQuery) -> bool:
    return config.DEBUG_MODE and callback.from_user.id == config.ADMIN_ID


async def show_test_menu(callback: CallbackQuery):
    if not _admin_only(callback):
        return await callback.answer("🚫 Недоступно", show_alert=True)
    await callback.answer()
    await callback.message.answer(
        "🧪 Тест-меню (DEBUG_MODE=True)\n"
        "• Создать 5 тестовых профилей — фейковые пользователи с реальными file_id фото\n"
        "• Переключить профиль — действовать от имени фейка (маппинг в test_sessions)\n"
        "• Смоделировать оценку — фейки оценивают друг друга или вас",
        reply_markup=kb.test_menu_kb())


@router.message(Command("test_profiles"))
async def cmd_test(message: Message):
    if not (config.DEBUG_MODE and message.from_user.id == config.ADMIN_ID):
        return
    await message.answer("🧪 Тест-меню", reply_markup=kb.test_menu_kb())


@router.callback_query(F.data == "test:create")
async def on_test_create(callback: CallbackQuery):
    if not _admin_only(callback):
        return await callback.answer("🚫", show_alert=True)
    await callback.answer("Создаю профили...")

    # Upload local assets once to obtain REAL file_ids reusable by fake profiles.
    pool, sent_ids = [], []
    for path in (config.PLACEHOLDER_IMG, config.SCALE_MALE_IMG, config.SCALE_FEMALE_IMG):
        if os.path.exists(path):
            m = await callback.bot.send_photo(callback.message.chat.id, FSInputFile(path))
            pool.append(m.photo[-1].file_id)
            sent_ids.append(m.message_id)

    names = []
    for name, gender in TEST_PROFILES:
        tid = db.unique_fake_id()
        db.create_user(tid, is_test=1)
        db.set_name(tid, name)
        db.set_gender(tid, gender)
        db.set_target_gender(tid, random.choice(["male", "female"]))
        db.set_unlocked(tid)  # test profiles are immediately rateable
        if pool:
            for fid in random.sample(pool, k=random.randint(1, len(pool))):
                db.add_photo(tid, fid)
        names.append(name)

    for mid in sent_ids:  # clean up the upload messages
        try:
            await callback.bot.delete_message(callback.message.chat.id, mid)
        except Exception:
            pass
    await callback.message.answer(f"✅ Созданы тестовые профили: {', '.join(names)}",
                                  reply_markup=kb.test_menu_kb())


@router.callback_query(F.data == "test:switch")
async def on_test_switch(callback: CallbackQuery):
    if not _admin_only(callback):
        return await callback.answer("🚫", show_alert=True)
    users = db.list_test_users()
    if not users:
        return await callback.answer("Сначала создайте тестовые профили", show_alert=True)
    await callback.answer()
    await callback.message.answer("🔁 Выберите профиль, от имени которого действовать "
                                  "(это имитирует /start для него):",
                                  reply_markup=kb.test_user_list_kb(users, "tsw"))


@router.callback_query(F.data.startswith("tsw:"))
async def on_test_switch_pick(callback: CallbackQuery, state: FSMContext):
    if not _admin_only(callback):
        return await callback.answer("🚫", show_alert=True)
    tid = int(callback.data.split(":")[1])
    db.set_session(callback.from_user.id, tid)   # identity overlay for all handlers
    await state.clear()
    row = db.get_user(tid)
    await callback.answer()
    await callback.message.answer(f"🎭 Теперь вы — {row['name']}. Запускаю /start от этого профиля:")
    if ut.profile_complete(row):
        await ut.show_main_menu(callback.bot, callback.message.chat.id, tid)
    else:
        await ut.run_start(callback.bot, callback.message.chat.id, tid, state)


@router.callback_query(F.data == "test:sim")
async def on_test_sim(callback: CallbackQuery):
    if not _admin_only(callback):
        return await callback.answer("🚫", show_alert=True)
    users = db.list_test_users()
    if not users:
        return await callback.answer("Сначала создайте тестовые профили", show_alert=True)
    extra = [InlineKeyboardButton(text="👑 Меня (админа)", callback_data="simself")]
    await callback.answer()
    await callback.message.answer("🎲 Кто оценивает (rater)?",
                                  reply_markup=kb.test_user_list_kb(users, "tsr", extra))


@router.callback_query(F.data == "simself")
async def on_sim_self(callback: CallbackQuery):
    """Use the admin's real identity as rater (to test unlock decrement on yourself)."""
    if not _admin_only(callback):
        return await callback.answer("🚫", show_alert=True)
    await _show_ratees(callback, callback.from_user.id)


@router.callback_query(F.data.startswith("tsr:"))
async def on_sim_rater(callback: CallbackQuery):
    if not _admin_only(callback):
        return await callback.answer("🚫", show_alert=True)
    await _show_ratees(callback, int(callback.data.split(":")[1]))


async def _show_ratees(callback: CallbackQuery, rater_id: int):
    users = [u for u in db.list_test_users() if u["telegram_id"] != rater_id]
    rows = [[InlineKeyboardButton(text=f"{u['name']}", callback_data=f"tsre:{rater_id}:{u['telegram_id']}")]
            for u in users]
    if rater_id != callback.from_user.id:
        rows.append([InlineKeyboardButton(text="👑 Меня (админа)",
                                          callback_data=f"tsre:{rater_id}:{callback.from_user.id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="test:sim")])
    await callback.answer()
    await callback.message.answer("Кого оцениваем?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("tsre:"))
async def on_sim_ratee(callback: CallbackQuery):
    if not _admin_only(callback):
        return await callback.answer("🚫", show_alert=True)
    _, rater_s, ratee_s = callback.data.split(":")
    await callback.answer()
    await callback.message.answer("Какая оценка (1-7)?",
                                  reply_markup=kb.sim_score_kb(int(rater_s), int(ratee_s)))


@router.callback_query(F.data.startswith("tsrs:"))
async def on_sim_score(callback: CallbackQuery):
    if not _admin_only(callback):
        return await callback.answer("🚫", show_alert=True)
    _, rater_s, ratee_s, score_s = callback.data.split(":")
    rater_id, ratee_id, score = int(rater_s), int(ratee_s), int(score_s)
    added = await ut.process_rating(callback.bot, rater_id, ratee_id, score)
    rater_row, ratee_row = db.get_user(rater_id), db.get_user(ratee_id)
    msg = (f"🎲 {rater_row['name']} → {ratee_row['name']}: {score}. "
           f"Новый средний у {ratee_row['name']}: {ut.avg_text(ratee_id)}"
           if added else "Оценка уже существовала (пара уникальна).")
    await callback.answer()
    await callback.message.answer(msg, reply_markup=kb.test_menu_kb())


@router.callback_query(F.data == "test:exit")
async def on_test_exit(callback: CallbackQuery, state: FSMContext):
    if not _admin_only(callback):
        return await callback.answer("🚫", show_alert=True)
    db.clear_session(callback.from_user.id)
    await state.clear()
    await callback.answer()
    await callback.message.answer("🚪 Тест-режим выключен. Вы снова сами собой.",
                                  reply_markup=kb.main_menu_kb(config.DEBUG_MODE))


@router.callback_query(F.data == "test:back")
async def on_test_back(callback: CallbackQuery):
    if not _admin_only(callback):
        return await callback.answer("🚫", show_alert=True)
    await callback.answer()
    await callback.message.answer("🧪 Тест-меню", reply_markup=kb.test_menu_kb())