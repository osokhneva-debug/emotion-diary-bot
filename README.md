# Дневник Эмоций — Telegram Bot

Telegram-бот для осознанного отслеживания эмоций. Несколько раз в день бот спрашивает пользователя о его эмоциональном состоянии, помогая развивать эмоциональный интеллект и находить паттерны в своих переживаниях.

## Функциональность

### Основные возможности
- **Случайные проверки** — 4 раза в день (с 9:00 до 22:00) бот присылает запрос о текущем состоянии
- **Выбор эмоций** — двухуровневая система: сначала категория, затем конкретная эмоция
- **Фиксация причины** — после выбора эмоции бот спрашивает, что её вызвало
- **Дневник** — просмотр истории записей с навигацией
- **Статистика** — streak, общее количество записей, частые эмоции
- **Еженедельное саммари** — каждое воскресенье бот присылает обзор эмоций за неделю

### Категории эмоций

| Категория | Эмоции |
|-----------|--------|
| 😊 Радость / Удовлетворение | радость, счастье, восторг, благодарность, вдохновение, гордость |
| 🧐 Интерес / Любопытство | интерес, любопытство, увлечённость, предвкушение, азарт |
| 😌 Спокойствие / Умиротворение | спокойствие, расслабленность, гармония, принятие, безопасность |
| ⚡ Энергичность / Воодушевление | бодрость, энтузиазм, возбуждение, решимость, драйв |
| 😲 Удивление / Шок | удивление, изумление, ошеломление, растерянность |
| 😰 Тревога / Беспокойство | тревога, беспокойство, нервозность, страх, напряжение, сомнение |
| 😢 Грусть / Печаль | грусть, печаль, тоска, разочарование, меланхолия, одиночество |
| 😠 Злость / Раздражение | злость, раздражение, гнев, обида, фрустрация, зависть |
| 😳 Стыд / Вина | стыд, вина, смущение, неловкость, самокритика, сожаление |
| 😴 Усталость / Истощение | усталость, истощение, апатия, выгорание, безразличие |

---

## Архитектура

### Технологический стек
- **Python 3.11+**
- **aiogram 3.x** — асинхронный фреймворк для Telegram Bot API
- **PostgreSQL** — база данных (рекомендуется Supabase для бесплатного хостинга)
- **asyncpg** — асинхронный драйвер PostgreSQL
- **APScheduler** — планировщик для случайных проверок
- **aiohttp** — HTTP-сервер для health checks

### Структура проекта
```
emotion-diary-bot/
├── bot.py           # Основная логика бота, хендлеры, FSM
├── database.py      # Работа с PostgreSQL
├── config.py        # Конфигурация (токены, переменные окружения)
├── emotions.py      # Словарь категорий и эмоций
├── requirements.txt # Зависимости
└── README.md
```

### База данных

#### Таблица `users`
```sql
CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    timezone INTEGER DEFAULT 3,           -- Часовой пояс (UTC+N)
    check_start_hour INTEGER DEFAULT 9,   -- Начало проверок
    check_end_hour INTEGER DEFAULT 22,    -- Конец проверок
    checks_per_day INTEGER DEFAULT 4      -- Количество проверок в день
);
```

#### Таблица `entries`
```sql
CREATE TABLE entries (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    category TEXT NOT NULL,        -- Категория эмоции
    emotion TEXT NOT NULL,         -- Конкретная эмоция
    reason TEXT,                   -- Причина (опционально)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Таблица `scheduled_checks` (для хранения запланированных проверок)
```sql
CREATE TABLE scheduled_checks (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    scheduled_time TIMESTAMP NOT NULL,
    sent BOOLEAN DEFAULT FALSE
);
```

---

## Реализация

### 1. Конфигурация (config.py)

```python
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
```

### 2. Словарь эмоций (emotions.py)

```python
EMOTIONS = {
    "😊 Радость": {
        "emoji": "😊",
        "emotions": ["радость", "счастье", "восторг", "благодарность", "вдохновение", "гордость"]
    },
    "🧐 Интерес": {
        "emoji": "🧐",
        "emotions": ["интерес", "любопытство", "увлечённость", "предвкушение", "азарт"]
    },
    "😌 Спокойствие": {
        "emoji": "😌",
        "emotions": ["спокойствие", "расслабленность", "гармония", "принятие", "безопасность"]
    },
    "⚡ Энергичность": {
        "emoji": "⚡",
        "emotions": ["бодрость", "энтузиазм", "возбуждение", "решимость", "драйв"]
    },
    "😲 Удивление": {
        "emoji": "😲",
        "emotions": ["удивление", "изумление", "ошеломление", "растерянность"]
    },
    "😰 Тревога": {
        "emoji": "😰",
        "emotions": ["тревога", "беспокойство", "нервозность", "страх", "напряжение", "сомнение"]
    },
    "😢 Грусть": {
        "emoji": "😢",
        "emotions": ["грусть", "печаль", "тоска", "разочарование", "меланхолия", "одиночество"]
    },
    "😠 Злость": {
        "emoji": "😠",
        "emotions": ["злость", "раздражение", "гнев", "обида", "фрустрация", "зависть"]
    },
    "😳 Стыд": {
        "emoji": "😳",
        "emotions": ["стыд", "вина", "смущение", "неловкость", "самокритика", "сожаление"]
    },
    "😴 Усталость": {
        "emoji": "😴",
        "emotions": ["усталость", "истощение", "апатия", "выгорание", "безразличие"]
    }
}
```

### 3. FSM States (в bot.py)

```python
from aiogram.fsm.state import State, StatesGroup

class EmotionStates(StatesGroup):
    waiting_for_current_time = State()  # Онбординг: определение часового пояса
    waiting_for_category = State()       # Выбор категории эмоции
    waiting_for_emotion = State()        # Выбор конкретной эмоции
    waiting_for_reason = State()         # Ввод причины
```

### 4. Логика случайных проверок

Ключевое отличие от бота благодарностей — вместо фиксированного времени напоминания используются случайные моменты в течение дня.

```python
import random
from datetime import datetime, timedelta

async def schedule_daily_checks(user_id: int, timezone: int, start_hour: int, end_hour: int, count: int):
    """Генерирует случайные времена проверок на день"""
    today = datetime.now().date()

    # Генерируем случайные минуты в диапазоне
    total_minutes = (end_hour - start_hour) * 60
    random_minutes = sorted(random.sample(range(total_minutes), count))

    check_times = []
    for minutes in random_minutes:
        hour = start_hour + minutes // 60
        minute = minutes % 60
        check_time = datetime.combine(today, datetime.min.time()) + timedelta(hours=hour, minutes=minute)
        check_times.append(check_time)

    # Сохраняем в БД
    await db.save_scheduled_checks(user_id, check_times)
    return check_times
```

### 5. Планировщик проверок

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

async def check_and_send_notifications():
    """Запускается каждую минуту, проверяет нужно ли отправить уведомление"""
    now = datetime.now(timezone.utc)

    # Получаем все несотправленные проверки, время которых наступило
    pending_checks = await db.get_pending_checks(now)

    for check in pending_checks:
        user_id = check['user_id']
        try:
            await send_emotion_check(user_id)
            await db.mark_check_sent(check['id'])
        except Exception as e:
            logging.error(f"Failed to send check to {user_id}: {e}")

async def regenerate_daily_schedules():
    """Запускается в полночь, генерирует расписание на новый день"""
    users = await db.get_all_users_with_settings()
    for user in users:
        await schedule_daily_checks(
            user['user_id'],
            user['timezone'],
            user['check_start_hour'],
            user['check_end_hour'],
            user['checks_per_day']
        )

async def send_weekly_summary():
    """Запускается в воскресенье вечером, отправляет саммари за неделю"""
    users = await db.get_all_users()
    for user in users:
        try:
            summary = await db.get_weekly_summary(user['user_id'])
            if summary['total'] > 0:
                await send_summary_message(user['user_id'], summary)
        except Exception as e:
            logging.error(f"Failed to send weekly summary to {user['user_id']}: {e}")

# В main():
scheduler.add_job(check_and_send_notifications, "cron", minute="*")
scheduler.add_job(regenerate_daily_schedules, "cron", hour=0, minute=0)
scheduler.add_job(send_weekly_summary, "cron", day_of_week="sun", hour=20, minute=0)
scheduler.start()
```

### 6. Еженедельное саммари

```python
async def send_summary_message(user_id: int, summary: dict):
    """Отправка еженедельного саммари"""
    text = "📊 *Твоя неделя в эмоциях*\n\n"

    text += f"Всего записей: {summary['total']}\n\n"

    if summary['top_categories']:
        text += "📈 *Топ категорий:*\n"
        for i, cat in enumerate(summary['top_categories'][:3], 1):
            text += f"{i}. {cat['category']} — {cat['count']} раз\n"
        text += "\n"

    if summary['top_emotions']:
        text += "🎭 *Частые эмоции:*\n"
        for i, em in enumerate(summary['top_emotions'][:5], 1):
            text += f"{i}. {em['emotion']} — {em['count']} раз\n"
        text += "\n"

    if summary['days_with_entries']:
        text += f"📅 Дней с записями: {summary['days_with_entries']}/7\n"

    await bot.send_message(user_id, text, parse_mode="Markdown")
```

### 7. Хендлер выбора эмоции

```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@dp.message(Command("check"))
async def cmd_check(message: Message, state: FSMContext):
    """Ручная проверка эмоций"""
    await send_emotion_check(message.from_user.id, message)

async def send_emotion_check(user_id: int, message: Message = None):
    """Отправка запроса на выбор эмоции"""
    # Создаём кнопки категорий (2 в ряд)
    buttons = []
    categories = list(EMOTIONS.keys())
    for i in range(0, len(categories), 2):
        row = [InlineKeyboardButton(text=cat, callback_data=f"cat_{i}") for cat in categories[i:i+2]]
        buttons.append(row)

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    text = "🎭 Как ты себя сейчас чувствуешь?\n\nВыбери категорию:"

    if message:
        await message.answer(text, reply_markup=keyboard)
    else:
        await bot.send_message(user_id, text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("cat_"))
async def select_category(callback: CallbackQuery, state: FSMContext):
    """Выбор категории — показываем конкретные эмоции"""
    cat_index = int(callback.data.split("_")[1])
    category = list(EMOTIONS.keys())[cat_index]

    await state.update_data(category=category)

    emotions = EMOTIONS[category]["emotions"]
    buttons = [[InlineKeyboardButton(text=em, callback_data=f"em_{i}")] for i, em in enumerate(emotions)]
    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="back_to_categories")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        f"{category}\n\nВыбери эмоцию точнее:",
        reply_markup=keyboard
    )
    await state.set_state(EmotionStates.waiting_for_emotion)
    await callback.answer()

@dp.callback_query(F.data.startswith("em_"), EmotionStates.waiting_for_emotion)
async def select_emotion(callback: CallbackQuery, state: FSMContext):
    """Выбор эмоции — спрашиваем причину"""
    data = await state.get_data()
    category = data['category']

    em_index = int(callback.data.split("_")[1])
    emotion = EMOTIONS[category]["emotions"][em_index]

    await state.update_data(emotion=emotion)
    await state.set_state(EmotionStates.waiting_for_reason)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="skip_reason")]
    ])

    await callback.message.edit_text(
        f"Ты чувствуешь: {emotion}\n\n"
        "Что вызвало эту эмоцию? Напиши или пропусти.",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.message(EmotionStates.waiting_for_reason)
async def save_with_reason(message: Message, state: FSMContext):
    """Сохранение с причиной"""
    data = await state.get_data()

    await db.save_entry(
        user_id=message.from_user.id,
        category=data['category'],
        emotion=data['emotion'],
        reason=message.text
    )

    await state.clear()
    await message.answer(
        f"✅ Записано!\n\n"
        f"{EMOTIONS[data['category']]['emoji']} {data['emotion']}\n"
        f"📝 {message.text}",
        reply_markup=main_menu
    )

@dp.callback_query(F.data == "skip_reason", EmotionStates.waiting_for_reason)
async def save_without_reason(callback: CallbackQuery, state: FSMContext):
    """Сохранение без причины"""
    data = await state.get_data()

    await db.save_entry(
        user_id=callback.from_user.id,
        category=data['category'],
        emotion=data['emotion'],
        reason=None
    )

    await state.clear()
    await callback.message.edit_text(
        f"✅ Записано!\n\n"
        f"{EMOTIONS[data['category']]['emoji']} {data['emotion']}"
    )
    await callback.answer()
```

### 8. Методы базы данных (database.py)

```python
async def save_entry(self, user_id: int, category: str, emotion: str, reason: str = None):
    """Сохранить запись эмоции"""
    async with self.pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO entries (user_id, category, emotion, reason, created_at)
               VALUES ($1, $2, $3, $4, $5)""",
            user_id, category, emotion, reason, datetime.now()
        )

async def get_entries(self, user_id: int, limit: int = 50) -> List[Dict]:
    """Получить записи пользователя"""
    async with self.pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT category, emotion, reason, created_at
               FROM entries WHERE user_id = $1
               ORDER BY created_at DESC LIMIT $2""",
            user_id, limit
        )
        return [dict(row) for row in rows]

async def get_emotion_stats(self, user_id: int) -> Dict:
    """Статистика по эмоциям"""
    async with self.pool.acquire() as conn:
        # Топ эмоций
        top_emotions = await conn.fetch(
            """SELECT emotion, COUNT(*) as count
               FROM entries WHERE user_id = $1
               GROUP BY emotion ORDER BY count DESC LIMIT 5""",
            user_id
        )

        # Топ категорий
        top_categories = await conn.fetch(
            """SELECT category, COUNT(*) as count
               FROM entries WHERE user_id = $1
               GROUP BY category ORDER BY count DESC LIMIT 5""",
            user_id
        )

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM entries WHERE user_id = $1", user_id
        )

        return {
            "total": total,
            "top_emotions": [dict(r) for r in top_emotions],
            "top_categories": [dict(r) for r in top_categories]
        }

async def save_scheduled_checks(self, user_id: int, check_times: List[datetime]):
    """Сохранить запланированные проверки"""
    async with self.pool.acquire() as conn:
        # Удаляем старые неотправленные
        await conn.execute(
            "DELETE FROM scheduled_checks WHERE user_id = $1 AND sent = FALSE",
            user_id
        )
        # Добавляем новые
        for check_time in check_times:
            await conn.execute(
                "INSERT INTO scheduled_checks (user_id, scheduled_time) VALUES ($1, $2)",
                user_id, check_time
            )

async def get_pending_checks(self, current_time: datetime) -> List[Dict]:
    """Получить несотправленные проверки, время которых наступило"""
    async with self.pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, user_id FROM scheduled_checks
               WHERE sent = FALSE AND scheduled_time <= $1""",
            current_time
        )
        return [dict(row) for row in rows]

async def mark_check_sent(self, check_id: int):
    """Отметить проверку как отправленную"""
    async with self.pool.acquire() as conn:
        await conn.execute(
            "UPDATE scheduled_checks SET sent = TRUE WHERE id = $1",
            check_id
        )

async def get_weekly_summary(self, user_id: int) -> Dict:
    """Получить статистику за последнюю неделю"""
    async with self.pool.acquire() as conn:
        week_ago = datetime.now() - timedelta(days=7)

        # Общее количество записей за неделю
        total = await conn.fetchval(
            """SELECT COUNT(*) FROM entries
               WHERE user_id = $1 AND created_at >= $2""",
            user_id, week_ago
        )

        # Топ категорий за неделю
        top_categories = await conn.fetch(
            """SELECT category, COUNT(*) as count
               FROM entries WHERE user_id = $1 AND created_at >= $2
               GROUP BY category ORDER BY count DESC LIMIT 3""",
            user_id, week_ago
        )

        # Топ эмоций за неделю
        top_emotions = await conn.fetch(
            """SELECT emotion, COUNT(*) as count
               FROM entries WHERE user_id = $1 AND created_at >= $2
               GROUP BY emotion ORDER BY count DESC LIMIT 5""",
            user_id, week_ago
        )

        # Количество дней с записями
        days_with_entries = await conn.fetchval(
            """SELECT COUNT(DISTINCT DATE(created_at))
               FROM entries WHERE user_id = $1 AND created_at >= $2""",
            user_id, week_ago
        )

        return {
            "total": total,
            "top_categories": [dict(r) for r in top_categories],
            "top_emotions": [dict(r) for r in top_emotions],
            "days_with_entries": days_with_entries
        }
```

---

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Запуск бота, онбординг |
| `/check` | Записать эмоцию сейчас |
| `/diary` | Открыть дневник записей |
| `/stats` | Статистика по эмоциям |
| `/settings` | Настройки (часовой пояс, частота проверок) |
| `/help` | Справка |

---

## Деплой на Render

### 1. Подготовка
1. Создать репозиторий на GitHub
2. Создать базу данных на Supabase (использовать Session pooler для IPv4)
3. Создать бота через @BotFather

### 2. Настройка Render
1. New → Web Service → Connect GitHub repo
2. Environment: Python 3
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python bot.py`
5. Environment Variables:
   - `BOT_TOKEN` — токен от BotFather
   - `DATABASE_URL` — строка подключения от Supabase
   - `ADMIN_IDS` — ID админов через запятую

### 3. requirements.txt
```
aiogram>=3.0.0
apscheduler>=3.10.0
asyncpg>=0.29.0
python-dotenv>=1.0.0
aiohttp>=3.9.0
```

---

## Особенности реализации

### Отличия от Дневника Благодарностей

| Аспект | Дневник Благодарностей | Дневник Эмоций |
|--------|----------------------|----------------|
| Напоминания | Фиксированное время (1 раз в день) | Случайные моменты (4 раза в день) |
| Ввод | Свободный текст | Выбор из списка + опциональный текст |
| Структура записи | Список благодарностей | Категория → Эмоция → Причина |
| Статистика | Streak, количество | Топ эмоций, паттерны по времени |

### Сложности и решения

1. **Случайные проверки** — генерируем расписание на день в полночь, храним в БД
2. **Часовые пояса** — все времена в БД хранятся в UTC, конвертируем при отображении
3. **Много кнопок** — используем двухуровневую навигацию (категория → эмоция)
4. **Пропущенные проверки** — просто не отправляем, не накапливаем

---

## Возможные улучшения

- [ ] Графики эмоций по дням/неделям
- [ ] Экспорт в CSV/PDF
- [ ] Напоминание о паттернах ("Ты часто чувствуешь тревогу по понедельникам")
- [ ] Интеграция с Whisper для голосового ввода причины
- [ ] Добавление своих эмоций пользователем
