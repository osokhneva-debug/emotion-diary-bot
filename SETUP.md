# Инструкция по запуску Emotion Diary Bot

## Шаг 1: Создание Telegram бота

1. Открой Telegram и найди **@BotFather**
2. Отправь команду `/newbot`
3. Введи название бота (например: "Дневник Эмоций")
4. Введи username бота (например: `emotion_diary_yourname_bot`)
5. **Сохрани токен** — он выглядит примерно так: `7123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw`

## Шаг 2: Создание базы данных на Supabase

1. Зайди на https://supabase.com и создай аккаунт (можно через GitHub)
2. Нажми **New Project**
3. Заполни:
   - **Name**: emotion-diary-bot
   - **Database Password**: придумай надёжный пароль и **запиши его!**
   - **Region**: выбери ближайший (например, Frankfurt для Европы)
4. Подожди ~2 минуты пока проект создастся

### Получение строки подключения:

1. Перейди в **Project Settings** (иконка шестерёнки слева)
2. Выбери **Database**
3. Прокрути до раздела **Connection string**
4. Выбери вкладку **URI**
5. В выпадающем списке выбери **Session** (не Transaction!)
6. Скопируй строку и замени `[YOUR-PASSWORD]` на свой пароль

Пример строки:
```
postgresql://postgres.abcdefghijk:ВашПароль@aws-0-eu-central-1.pooler.supabase.com:5432/postgres
```

## Шаг 3: Настройка проекта локально

### 3.1. Установи Python 3.11+

Проверь версию:
```bash
python3 --version
```

### 3.2. Создай виртуальное окружение (рекомендуется)

```bash
cd /Users/o.sokhneva/Documents/emotion-diary-bot
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
```

### 3.3. Установи зависимости

```bash
pip install -r requirements.txt
```

### 3.4. Создай файл .env

```bash
cp .env.example .env
```

Открой `.env` и заполни:
- `BOT_TOKEN` — токен от BotFather
- `DATABASE_URL` — строка подключения от Supabase
- `ADMIN_IDS` — твой Telegram ID (узнать можно у @userinfobot)

## Шаг 4: Запуск бота локально

```bash
python bot.py
```

Если всё настроено правильно, увидишь:
```
INFO:__main__:Database connected
INFO:__main__:Scheduler started
INFO:__main__:Health check server started on port 8080
INFO:__main__:Bot started
```

Теперь открой своего бота в Telegram и отправь `/start`!

---

## Шаг 5: Деплой на Render (бесплатный хостинг)

### 5.1. Загрузи код на GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/emotion-diary-bot.git
git push -u origin main
```

**Важно:** Не забудь добавить `.env` в `.gitignore`!

### 5.2. Создай .gitignore

```bash
echo ".env
venv/
__pycache__/
*.pyc" > .gitignore
```

### 5.3. Настройка Render

1. Зайди на https://render.com и создай аккаунт
2. Нажми **New** → **Web Service**
3. Подключи свой GitHub репозиторий
4. Настрой сервис:
   - **Name**: emotion-diary-bot
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
5. Добавь **Environment Variables**:
   - `BOT_TOKEN` = твой токен
   - `DATABASE_URL` = строка подключения Supabase
   - `ADMIN_IDS` = твой Telegram ID
6. Нажми **Create Web Service**

Бот запустится через 2-3 минуты!

---

## Возможные проблемы

### Ошибка подключения к базе данных

```
asyncpg.exceptions.InvalidPasswordError
```
**Решение:** Проверь пароль в DATABASE_URL и убедись, что используешь Session pooler (не Transaction).

### Бот не отвечает

1. Проверь, что токен правильный
2. Убедись, что бот запущен (в логах есть "Bot started")
3. Попробуй перезапустить: Ctrl+C и `python bot.py`

### Ошибка "Address already in use" (порт 8080)

```bash
lsof -i :8080  # Найти процесс
kill -9 PID    # Убить процесс
```

---

## Полезные команды

```bash
# Активировать виртуальное окружение
source venv/bin/activate

# Запустить бота
python bot.py

# Остановить бота
Ctrl+C

# Обновить зависимости
pip install -r requirements.txt --upgrade
```
