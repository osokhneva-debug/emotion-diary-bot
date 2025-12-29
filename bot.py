import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone as tz

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

from config import BOT_TOKEN
from database import db
from emotions import EMOTIONS, CATEGORIES, BODY_SENSATIONS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
scheduler = AsyncIOScheduler()


# === FSM States ===

class OnboardingStates(StatesGroup):
    waiting_for_intro_read = State()
    waiting_for_timezone = State()


class EmotionStates(StatesGroup):
    waiting_for_emotion_input = State()  # Free text or button
    waiting_for_category = State()
    waiting_for_emotion = State()
    waiting_for_intensity = State()
    waiting_for_body_sensation = State()
    waiting_for_reason = State()
    waiting_for_note = State()


class SettingsStates(StatesGroup):
    waiting_for_start_hour = State()
    waiting_for_end_hour = State()
    waiting_for_checks_count = State()


# === Keyboards ===

def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Как я сейчас?", callback_data="check")],
        [InlineKeyboardButton(text="Дневник", callback_data="diary"),
         InlineKeyboardButton(text="Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="Настройки", callback_data="settings")]
    ])


def get_emotion_start_keyboard():
    """Initial keyboard for emotion check - free input or show ideas"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Показать идеи эмоций", callback_data="show_emotions")]
    ])


def get_categories_keyboard():
    """Categories in 3 columns"""
    buttons = []
    for i in range(0, len(CATEGORIES), 3):
        row = []
        for j in range(3):
            if i + j < len(CATEGORIES):
                cat = CATEGORIES[i + j]
                row.append(InlineKeyboardButton(text=cat, callback_data=f"cat_{i + j}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="Другое...", callback_data="other_emotion")])
    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="back_to_input")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_emotions_keyboard(category: str):
    """Specific emotions within a category"""
    emotions = EMOTIONS[category]["emotions"]
    buttons = []
    for i in range(0, len(emotions), 2):
        row = []
        for j in range(2):
            if i + j < len(emotions):
                em = emotions[i + j]
                row.append(InlineKeyboardButton(text=em, callback_data=f"em_{i + j}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="Другое...", callback_data="other_emotion")])
    buttons.append([InlineKeyboardButton(text="← К категориям", callback_data="show_emotions")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_intensity_keyboard():
    """Scale 0-10"""
    buttons = []
    # First row: 0-5
    buttons.append([InlineKeyboardButton(text=str(i), callback_data=f"intensity_{i}") for i in range(6)])
    # Second row: 6-10
    buttons.append([InlineKeyboardButton(text=str(i), callback_data=f"intensity_{i}") for i in range(6, 11)])
    buttons.append([InlineKeyboardButton(text="Пропустить", callback_data="skip_intensity")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_body_sensations_keyboard():
    """Quick body sensation options"""
    buttons = []
    for i in range(0, len(BODY_SENSATIONS), 2):
        row = []
        for j in range(2):
            if i + j < len(BODY_SENSATIONS):
                sens = BODY_SENSATIONS[i + j]
                row.append(InlineKeyboardButton(text=sens, callback_data=f"body_{i + j}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="Написать своё", callback_data="body_custom")])
    buttons.append([InlineKeyboardButton(text="Пропустить", callback_data="skip_body")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_skip_keyboard(callback_data: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data=callback_data)]
    ])


def get_note_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить заметку", callback_data="add_note")],
        [InlineKeyboardButton(text="Завершить", callback_data="finish_entry")]
    ])


def get_timezone_keyboard():
    buttons = []
    for offset in range(-1, 13, 2):
        row = []
        for o in [offset, offset + 1]:
            if -1 <= o <= 12:
                sign = "+" if o >= 0 else ""
                row.append(InlineKeyboardButton(text=f"UTC{sign}{o}", callback_data=f"tz_{o}"))
        if row:
            buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_ping_keyboard():
    """Keyboard for scheduled emotion check pings"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ответить", callback_data="check")],
        [InlineKeyboardButton(text="Напомнить через 15 мин", callback_data="delay_15")],
        [InlineKeyboardButton(text="Пропустить сегодня", callback_data="skip_today")]
    ])


# === ONBOARDING ===

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)

    if user and user.get('onboarding_complete'):
        await message.answer(
            "С возвращением! Рада тебя видеть.\n\n"
            "Как ты сейчас?",
            reply_markup=get_main_menu()
        )
    else:
        # Start onboarding
        intro_text = (
            "Привет! Я — твой дневник эмоций.\n\n"
            "Зачем это нужно? Исследования показывают, что простое называние эмоций "
            "(affect labeling) помогает снизить их интенсивность и лучше понимать себя. "
            "Когда мы замечаем и называем то, что чувствуем, мы уже делаем шаг к ясности.\n\n"
            "Как это работает:\n"
            "• Я буду иногда спрашивать тебя, как ты себя чувствуешь\n"
            "• Ты можешь описать своими словами или выбрать из подсказок\n"
            "• По желанию — отметить интенсивность и что вызвало эмоцию\n"
            "• Раз в неделю пришлю мягкую сводку\n\n"
            "Никаких оценок, только наблюдение. Твои записи видишь только ты."
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Понятно, продолжим", callback_data="onboarding_continue")]
        ])

        await message.answer(intro_text, reply_markup=keyboard)
        await state.set_state(OnboardingStates.waiting_for_intro_read)


@dp.callback_query(F.data == "onboarding_continue", OnboardingStates.waiting_for_intro_read)
async def onboarding_timezone(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Отлично! Чтобы присылать напоминания в удобное время, "
        "подскажи свой часовой пояс:",
        reply_markup=get_timezone_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_for_timezone)
    await callback.answer()


@dp.callback_query(F.data.startswith("tz_"), OnboardingStates.waiting_for_timezone)
async def save_timezone_onboarding(callback: CallbackQuery, state: FSMContext):
    timezone = int(callback.data.split("_")[1])
    await db.add_user(callback.from_user.id, timezone)
    await db.complete_onboarding(callback.from_user.id)

    # Schedule checks for the new user
    await schedule_daily_checks(callback.from_user.id, timezone, 9, 22, 4)

    await state.clear()
    await callback.message.edit_text(
        f"Готово! Часовой пояс UTC+{timezone} сохранён.\n\n"
        "Я буду присылать 4 мягких напоминания в день с 9:00 до 22:00. "
        "Это можно изменить в настройках.\n\n"
        "Хочешь записать, как ты сейчас?",
        reply_markup=get_main_menu()
    )
    await callback.answer()


# === EMOTION CHECK FLOW ===

@dp.message(Command("check"))
async def cmd_check(message: Message, state: FSMContext):
    await start_emotion_check(message.from_user.id, state, message=message)


@dp.callback_query(F.data == "check")
async def callback_check(callback: CallbackQuery, state: FSMContext):
    await start_emotion_check(callback.from_user.id, state, callback=callback)
    await callback.answer()


async def start_emotion_check(user_id: int, state: FSMContext, message: Message = None, callback: CallbackQuery = None):
    """Start the emotion check flow with empathetic question"""
    text = (
        "Как ты сейчас?\n\n"
        "Если хочется — напиши 1–2 слова или опиши своими словами. "
        "Или нажми кнопку, чтобы посмотреть идеи."
    )

    await state.set_state(EmotionStates.waiting_for_emotion_input)
    await state.update_data(category=None, emotion=None, intensity=None, body_sensation=None, reason=None)

    if callback:
        await callback.message.edit_text(text, reply_markup=get_emotion_start_keyboard())
    elif message:
        await message.answer(text, reply_markup=get_emotion_start_keyboard())
    else:
        await bot.send_message(user_id, text, reply_markup=get_emotion_start_keyboard())


@dp.message(EmotionStates.waiting_for_emotion_input)
async def handle_free_emotion_input(message: Message, state: FSMContext):
    """User typed their emotion freely"""
    emotion_text = message.text.strip()
    await state.update_data(emotion=emotion_text, category=None, intensity=None)

    # Skip intensity, go directly to body sensations
    await message.answer(
        f"*{emotion_text}* — записала.\n\n"
        "Есть ли телесные ощущения, которые ты замечаешь?\n"
        "(напряжение, тепло, сжатие...)",
        reply_markup=get_body_sensations_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(EmotionStates.waiting_for_body_sensation)


@dp.callback_query(F.data == "show_emotions", EmotionStates.waiting_for_emotion_input)
async def show_emotion_categories(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Выбери категорию, которая ближе всего:",
        reply_markup=get_categories_keyboard()
    )
    await state.set_state(EmotionStates.waiting_for_category)
    await callback.answer()


@dp.callback_query(F.data == "show_emotions")
async def show_emotion_categories_general(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Выбери категорию, которая ближе всего:",
        reply_markup=get_categories_keyboard()
    )
    await state.set_state(EmotionStates.waiting_for_category)
    await callback.answer()


@dp.callback_query(F.data == "back_to_input")
async def back_to_emotion_input(callback: CallbackQuery, state: FSMContext):
    await start_emotion_check(callback.from_user.id, state, callback=callback)
    await callback.answer()


@dp.callback_query(F.data.startswith("cat_"), EmotionStates.waiting_for_category)
async def select_category(callback: CallbackQuery, state: FSMContext):
    cat_index = int(callback.data.split("_")[1])
    category = CATEGORIES[cat_index]

    await state.update_data(category=category)
    await state.set_state(EmotionStates.waiting_for_emotion)

    emoji = EMOTIONS[category]["emoji"]
    await callback.message.edit_text(
        f"{emoji} {category}\n\nВыбери то, что точнее описывает:",
        reply_markup=get_emotions_keyboard(category)
    )
    await callback.answer()


@dp.callback_query(F.data == "other_emotion")
async def other_emotion_input(callback: CallbackQuery, state: FSMContext):
    """User wants to type their own emotion"""
    await callback.message.edit_text(
        "Напиши своими словами, что ты сейчас чувствуешь:"
    )
    await state.set_state(EmotionStates.waiting_for_emotion_input)
    await callback.answer()


@dp.callback_query(F.data.startswith("em_"), EmotionStates.waiting_for_emotion)
async def select_emotion(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    category = data.get('category')

    if not category:
        await callback.answer("Что-то пошло не так, начни сначала", show_alert=True)
        return

    em_index = int(callback.data.split("_")[1])
    emotion = EMOTIONS[category]["emotions"][em_index]

    await state.update_data(emotion=emotion, intensity=None)

    # Skip intensity, go directly to body sensations
    await callback.message.edit_text(
        f"*{emotion}* — понятно.\n\n"
        "Есть ли телесные ощущения, которые ты замечаешь?\n"
        "(напряжение, тепло, сжатие...)",
        reply_markup=get_body_sensations_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(EmotionStates.waiting_for_body_sensation)
    await callback.answer()


# === INTENSITY ===

@dp.callback_query(F.data.startswith("intensity_"), EmotionStates.waiting_for_intensity)
async def select_intensity(callback: CallbackQuery, state: FSMContext):
    intensity = int(callback.data.split("_")[1])
    await state.update_data(intensity=intensity)

    await callback.message.edit_text(
        "Есть ли телесные ощущения, которые ты замечаешь?\n"
        "(напряжение, тепло, сжатие...)",
        reply_markup=get_body_sensations_keyboard()
    )
    await state.set_state(EmotionStates.waiting_for_body_sensation)
    await callback.answer()


@dp.callback_query(F.data == "skip_intensity", EmotionStates.waiting_for_intensity)
async def skip_intensity(callback: CallbackQuery, state: FSMContext):
    await state.update_data(intensity=None)

    await callback.message.edit_text(
        "Есть ли телесные ощущения, которые ты замечаешь?\n"
        "(напряжение, тепло, сжатие...)",
        reply_markup=get_body_sensations_keyboard()
    )
    await state.set_state(EmotionStates.waiting_for_body_sensation)
    await callback.answer()


# === BODY SENSATIONS ===

@dp.callback_query(F.data.startswith("body_"), EmotionStates.waiting_for_body_sensation)
async def select_body_sensation(callback: CallbackQuery, state: FSMContext):
    if callback.data == "body_custom":
        await callback.message.edit_text(
            "Опиши телесные ощущения своими словами:"
        )
        # Stay in same state, but expect text input
        await callback.answer()
        return

    body_index = int(callback.data.split("_")[1])
    body_sensation = BODY_SENSATIONS[body_index]
    await state.update_data(body_sensation=body_sensation)

    await ask_for_reason(callback.message, state)
    await callback.answer()


@dp.callback_query(F.data == "skip_body", EmotionStates.waiting_for_body_sensation)
async def skip_body_sensation(callback: CallbackQuery, state: FSMContext):
    await state.update_data(body_sensation=None)
    await ask_for_reason(callback.message, state)
    await callback.answer()


@dp.message(EmotionStates.waiting_for_body_sensation)
async def handle_body_sensation_text(message: Message, state: FSMContext):
    await state.update_data(body_sensation=message.text.strip())
    await ask_for_reason(message, state, edit=False)


# === REASON/CONTEXT ===

async def ask_for_reason(message: Message, state: FSMContext, edit: bool = True):
    text = (
        "Напиши что поспособствовало этому\n"
        "(событие, мысль, человек, место...)"
    )

    if edit:
        await message.edit_text(text, reply_markup=get_skip_keyboard("skip_reason"))
    else:
        await message.answer(text, reply_markup=get_skip_keyboard("skip_reason"))

    await state.set_state(EmotionStates.waiting_for_reason)


@dp.message(EmotionStates.waiting_for_reason)
async def handle_reason_input(message: Message, state: FSMContext):
    await state.update_data(reason=message.text.strip())
    await finish_entry_flow(message, state, edit=False)


@dp.callback_query(F.data == "skip_reason", EmotionStates.waiting_for_reason)
async def skip_reason(callback: CallbackQuery, state: FSMContext):
    await state.update_data(reason=None)
    await finish_entry_flow(callback.message, state, edit=True)
    await callback.answer()


# === FINISH & NOTE ===

async def finish_entry_flow(message: Message, state: FSMContext, edit: bool = True):
    """Show completion message with option to add note"""
    data = await state.get_data()
    emotion = data.get('emotion', 'эмоция')

    completion_text = (
        f"Спасибо! Уже сам факт, что ты это заметил(а) и назвал(а), — шаг к ясности.\n\n"
        f"Записано: *{emotion}*"
    )

    if data.get('intensity') is not None:
        completion_text += f" (интенсивность: {data['intensity']}/10)"

    completion_text += "\n\nХочешь добавить заметку на будущее?"

    if edit:
        await message.edit_text(completion_text, reply_markup=get_note_keyboard(), parse_mode="Markdown")
    else:
        await message.answer(completion_text, reply_markup=get_note_keyboard(), parse_mode="Markdown")

    await state.set_state(EmotionStates.waiting_for_note)


@dp.callback_query(F.data == "add_note", EmotionStates.waiting_for_note)
async def add_note_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Напиши заметку:")
    await callback.answer()


@dp.message(EmotionStates.waiting_for_note)
async def handle_note_input(message: Message, state: FSMContext):
    await state.update_data(note=message.text.strip())
    await save_entry_and_finish(message, state, edit=False)


@dp.callback_query(F.data == "finish_entry", EmotionStates.waiting_for_note)
async def finish_without_note(callback: CallbackQuery, state: FSMContext):
    await state.update_data(note=None)
    await save_entry_and_finish(callback.message, state, edit=True)
    await callback.answer()


async def save_entry_and_finish(message: Message, state: FSMContext, edit: bool = True):
    """Save entry to database and show final message"""
    data = await state.get_data()
    user_id = message.chat.id

    await db.save_entry(
        user_id=user_id,
        emotion=data.get('emotion', ''),
        category=data.get('category'),
        intensity=data.get('intensity'),
        body_sensation=data.get('body_sensation'),
        reason=data.get('reason'),
        note=data.get('note')
    )

    # Build summary
    summary_parts = [f"*{data.get('emotion', '')}*"]
    if data.get('intensity') is not None:
        summary_parts.append(f"({data['intensity']}/10)")
    if data.get('body_sensation'):
        summary_parts.append(f"\nТело: {data['body_sensation']}")
    if data.get('reason'):
        summary_parts.append(f"\nПричина: {data['reason']}")
    if data.get('note'):
        summary_parts.append(f"\nЗаметка: {data['note']}")

    final_text = (
        "Записано!\n\n"
        f"{' '.join(summary_parts[:2])}"
        f"{''.join(summary_parts[2:])}\n\n"
        "Береги себя."
    )

    await state.clear()

    if edit:
        await message.edit_text(final_text, reply_markup=get_main_menu(), parse_mode="Markdown")
    else:
        await message.answer(final_text, reply_markup=get_main_menu(), parse_mode="Markdown")


# === PING ACTIONS (Delay/Skip) ===

@dp.callback_query(F.data == "delay_15")
async def delay_check(callback: CallbackQuery):
    await db.add_delayed_check(callback.from_user.id, delay_minutes=15)
    await callback.message.edit_text(
        "Хорошо, напомню через 15 минут."
    )
    await callback.answer()


@dp.callback_query(F.data == "skip_today")
async def skip_today(callback: CallbackQuery):
    await db.skip_today_checks(callback.from_user.id)
    await callback.message.edit_text(
        "Понятно, сегодня больше не буду беспокоить. До завтра!"
    )
    await callback.answer()


# === DIARY ===

@dp.message(Command("diary"))
async def cmd_diary(message: Message):
    await show_diary(message.from_user.id, message)


@dp.callback_query(F.data == "diary")
async def callback_diary(callback: CallbackQuery):
    await show_diary(callback.from_user.id, callback.message, edit=True)
    await callback.answer()


@dp.callback_query(F.data.startswith("diary_page_"))
async def diary_page(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    await show_diary(callback.from_user.id, callback.message, page=page, edit=True)
    await callback.answer()


async def show_diary(user_id: int, message: Message, page: int = 0, edit: bool = False):
    per_page = 5
    entries = await db.get_entries(user_id, limit=per_page, offset=page * per_page)
    total = await db.get_entries_count(user_id)

    if not entries:
        text = "Дневник пока пуст.\n\nЗапиши своё первое наблюдение!"
        keyboard = get_main_menu()
    else:
        text = "*Твой дневник:*\n\n"
        for entry in entries:
            date_str = entry['created_at'].strftime("%d.%m %H:%M")
            intensity_str = f" ({entry['intensity']}/10)" if entry.get('intensity') is not None else ""

            text += f"*{entry['emotion']}*{intensity_str} — {date_str}\n"
            if entry.get('reason'):
                text += f"   _{entry['reason']}_\n"
            text += "\n"

        # Pagination
        buttons = []
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text="← Назад", callback_data=f"diary_page_{page - 1}"))
        if (page + 1) * per_page < total:
            nav_row.append(InlineKeyboardButton(text="Вперёд →", callback_data=f"diary_page_{page + 1}"))
        if nav_row:
            buttons.append(nav_row)
        buttons.append([InlineKeyboardButton(text="Меню", callback_data="menu")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


# === STATS ===

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    await show_stats(message.from_user.id, message)


@dp.callback_query(F.data == "stats")
async def callback_stats(callback: CallbackQuery):
    await show_stats(callback.from_user.id, callback.message, edit=True)
    await callback.answer()


async def show_stats(user_id: int, message: Message, edit: bool = False):
    stats = await db.get_emotion_stats(user_id)

    if stats['total'] == 0:
        text = "Статистика пока пуста.\n\nЗапиши своё первое наблюдение!"
    else:
        text = "*Твоя статистика*\n\n"
        text += f"Всего записей: {stats['total']}\n"
        text += f"Streak: {stats['streak']} дней\n"

        if stats.get('avg_intensity'):
            text += f"Средняя интенсивность: {stats['avg_intensity']}/10\n"

        text += "\n"

        if stats['top_emotions']:
            text += "*Частые эмоции:*\n"
            for i, em in enumerate(stats['top_emotions'], 1):
                text += f"{i}. {em['emotion']} — {em['count']} раз\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Меню", callback_data="menu")]
    ])

    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


# === SETTINGS ===

@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    await show_settings(message.from_user.id, message)


@dp.callback_query(F.data == "settings")
async def callback_settings(callback: CallbackQuery):
    await show_settings(callback.from_user.id, callback.message, edit=True)
    await callback.answer()


async def show_settings(user_id: int, message: Message, edit: bool = False):
    user = await db.get_user(user_id)
    if not user:
        await db.add_user(user_id)
        user = await db.get_user(user_id)

    text = (
        "*Настройки*\n\n"
        f"Часовой пояс: UTC+{user['timezone']}\n"
        f"Напоминания: с {user['check_start_hour']}:00 до {user['check_end_hour']}:00\n"
        f"Раз в день: {user['checks_per_day']}\n"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить часовой пояс", callback_data="change_tz")],
        [InlineKeyboardButton(text="Изменить частоту", callback_data="change_frequency")],
        [InlineKeyboardButton(text="Меню", callback_data="menu")]
    ])

    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


@dp.callback_query(F.data == "change_tz")
async def change_timezone(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Выбери часовой пояс:",
        reply_markup=get_timezone_keyboard()
    )
    await state.set_state(SettingsStates.waiting_for_start_hour)
    await callback.answer()


@dp.callback_query(F.data.startswith("tz_"), SettingsStates.waiting_for_start_hour)
async def save_new_timezone(callback: CallbackQuery, state: FSMContext):
    timezone = int(callback.data.split("_")[1])
    await db.update_user_timezone(callback.from_user.id, timezone)

    user = await db.get_user(callback.from_user.id)
    await schedule_daily_checks(
        callback.from_user.id,
        timezone,
        user['check_start_hour'],
        user['check_end_hour'],
        user['checks_per_day']
    )

    await state.clear()
    await callback.message.edit_text(
        f"Часовой пояс изменён на UTC+{timezone}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Настройки", callback_data="settings")],
            [InlineKeyboardButton(text="Меню", callback_data="menu")]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "change_frequency")
async def change_frequency(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="2 раза", callback_data="freq_2"),
         InlineKeyboardButton(text="3 раза", callback_data="freq_3")],
        [InlineKeyboardButton(text="4 раза", callback_data="freq_4"),
         InlineKeyboardButton(text="5 раз", callback_data="freq_5")],
        [InlineKeyboardButton(text="← Назад", callback_data="settings")]
    ])
    await callback.message.edit_text(
        "Сколько раз в день присылать напоминания?",
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("freq_"))
async def save_frequency(callback: CallbackQuery):
    frequency = int(callback.data.split("_")[1])
    user = await db.get_user(callback.from_user.id)
    await db.update_user_settings(
        callback.from_user.id,
        user['check_start_hour'],
        user['check_end_hour'],
        frequency
    )

    await schedule_daily_checks(
        callback.from_user.id,
        user['timezone'],
        user['check_start_hour'],
        user['check_end_hour'],
        frequency
    )

    await callback.message.edit_text(
        f"Теперь я буду присылать {frequency} напоминаний в день.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Настройки", callback_data="settings")],
            [InlineKeyboardButton(text="Меню", callback_data="menu")]
        ])
    )
    await callback.answer()


# === MENU ===

@dp.callback_query(F.data == "menu")
async def callback_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Как я могу помочь?",
        reply_markup=get_main_menu()
    )
    await callback.answer()


# === HELP ===

@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "*Дневник эмоций*\n\n"
        "*Команды:*\n"
        "/start — начать\n"
        "/check — записать эмоцию\n"
        "/diary — дневник\n"
        "/stats — статистика\n"
        "/settings — настройки\n\n"
        "*Как это работает:*\n"
        "Я присылаю мягкие напоминания несколько раз в день. "
        "Ты можешь написать своими словами или выбрать из подсказок. "
        "Каждое воскресенье — сводка за неделю.\n\n"
        "Само называние эмоций помогает их осознать и снизить интенсивность."
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_menu())


# === SCHEDULER ===

async def schedule_daily_checks(user_id: int, timezone: int, start_hour: int, end_hour: int, count: int):
    today = datetime.now().date()

    total_minutes = (end_hour - start_hour) * 60
    if total_minutes <= count:
        random_minutes = list(range(0, total_minutes, max(1, total_minutes // count)))[:count]
    else:
        random_minutes = sorted(random.sample(range(total_minutes), count))

    check_times = []
    for minutes in random_minutes:
        hour = start_hour + minutes // 60
        minute = minutes % 60
        check_time = datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
        check_time_utc = check_time - timedelta(hours=timezone)
        check_times.append(check_time_utc)

    await db.save_scheduled_checks(user_id, check_times)
    logger.info(f"Scheduled {count} checks for user {user_id}")


async def check_and_send_notifications():
    now = datetime.now(tz.utc).replace(tzinfo=None)
    pending_checks = await db.get_pending_checks(now)

    # Group by user_id to avoid duplicate messages
    users_notified = set()

    for check in pending_checks:
        user_id = check['user_id']
        await db.mark_check_sent(check['id'])  # Mark as sent regardless

        if user_id in users_notified:
            continue  # Already sent to this user

        try:
            await bot.send_message(
                user_id,
                "Привет! Как ты сейчас?",
                reply_markup=get_ping_keyboard()
            )
            users_notified.add(user_id)
            logger.info(f"Sent check to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send check to {user_id}: {e}")


async def regenerate_daily_schedules():
    logger.info("Regenerating daily schedules...")
    users = await db.get_all_users_with_settings()
    for user in users:
        await schedule_daily_checks(
            user['user_id'],
            user['timezone'],
            user['check_start_hour'],
            user['check_end_hour'],
            user['checks_per_day']
        )
    logger.info(f"Regenerated schedules for {len(users)} users")


async def send_weekly_summary():
    logger.info("Sending weekly summaries...")
    users = await db.get_all_users()
    for user in users:
        try:
            summary = await db.get_weekly_summary(user['user_id'])
            if summary['total'] > 0:
                text = "*Твоя неделя в эмоциях*\n\n"
                text += f"Записей: {summary['total']}\n"
                text += f"Дней с записями: {summary['days_with_entries']}/7\n\n"

                if summary['top_emotions']:
                    emotions_list = ", ".join([e['emotion'] for e in summary['top_emotions'][:3]])
                    text += f"*Чаще всего:* {emotions_list}\n"

                if summary['top_reasons']:
                    reasons_list = ", ".join([r['reason'][:30] for r in summary['top_reasons'][:2]])
                    text += f"*Частые причины:* {reasons_list}\n"

                if summary['peak_time']:
                    text += f"*Пик записей:* {summary['peak_time']}\n"

                if summary['avg_intensity']:
                    text += f"*Средняя интенсивность:* {summary['avg_intensity']}/10\n"

                text += "\nБереги себя!"

                await bot.send_message(user['user_id'], text, parse_mode="Markdown")
                logger.info(f"Sent weekly summary to user {user['user_id']}")
        except Exception as e:
            logger.error(f"Failed to send weekly summary to {user['user_id']}: {e}")


# === HEALTH CHECK ===

async def health_check(request):
    return web.Response(text="OK")


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logger.info("Health check server started on port 8080")


# === MAIN ===

async def main():
    await db.connect()
    logger.info("Database connected")

    scheduler.add_job(check_and_send_notifications, "cron", minute="*")
    scheduler.add_job(regenerate_daily_schedules, "cron", hour=0, minute=0)
    scheduler.add_job(send_weekly_summary, "cron", day_of_week="sun", hour=20, minute=0)
    scheduler.start()
    logger.info("Scheduler started")

    await regenerate_daily_schedules()
    await start_health_server()

    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        await db.disconnect()
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
