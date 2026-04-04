import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import psycopg2
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash  # для создания пароля, но можно упростить

BOT_TOKEN = "8660176046:AAFgh3bPfUtm8EINKtqxSZOLXs5x2iOV6Iw"  # ваш токен

def get_db_connection():
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://tracker:tracker123@db:5432/expenses')
    return psycopg2.connect(DATABASE_URL)

# Вспомогательная функция: получить user_id по telegram_id (или создать нового)
def get_or_create_user(telegram_id, username=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
    row = cur.fetchone()
    if row:
        user_id = row[0]
    else:
        # Создаём нового пользователя
        # Если username не передан, генерируем из telegram_id
        if not username:
            username = f"tg_{telegram_id}"
        # Генерируем случайный пароль (пользователь будет входить в веб, если захочет)
        import secrets
        password = secrets.token_urlsafe(12)
        password_hash = generate_password_hash(password)
        try:
            cur.execute(
                "INSERT INTO users (username, password_hash, telegram_id) VALUES (%s, %s, %s) RETURNING id",
                (username, password_hash, telegram_id)
            )
            user_id = cur.fetchone()[0]
            conn.commit()
            print(f"Created new user: {username} with telegram_id {telegram_id}")
        except Exception as e:
            # Если username занят, добавим суффикс
            username = f"tg_{telegram_id}_{int(datetime.now().timestamp())}"
            cur.execute(
                "INSERT INTO users (username, password_hash, telegram_id) VALUES (%s, %s, %s) RETURNING id",
                (username, password_hash, telegram_id)
            )
            user_id = cur.fetchone()[0]
            conn.commit()
    cur.close()
    conn.close()
    return user_id

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    user_id = get_or_create_user(telegram_id, update.effective_user.username)
    context.user_data['user_id'] = user_id
    await update.message.reply_text(
        "🌟 Добро пожаловать в многопользовательский финансовый трекер!\n"
        "Твои данные изолированы от других пользователей.\n\n"
        "Используй /help для списка команд."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 *Доступные команды:*\n\n"
        "/start — Приветствие и регистрация\n"
        "/help  — Это сообщение\n"
        "/balance — Показать баланс\n"
        "/income сумма описание — Добавить доход\n"
        "/expense сумма описание — Добавить расход (или просто сумма описание)\n\n"
        "/link username пароль — Привязать Telegram к существующему аккаунту на сайте\n\n"
        "/logout — Отвязать Telegram-аккаунт и выйти\n\n"
        "💰 *Добавить расход:* просто напиши сумму и описание\n"
        "Пример: `300 такси`\n\n"
        "📈 *Доход:* `/income 5000 зарплата`\n\n"
        "🌐 Веб-трекер: http://10.93.26.99:5002"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'user_id' not in context.user_data:
        await update.message.reply_text("Сначала используй /start")
        return
    user_id = context.user_data['user_id']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id=%s AND type='income'", (user_id,))
    income = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id=%s AND type='expense'", (user_id,))
    expense = cur.fetchone()[0]
    total = income - expense
    cur.close()
    conn.close()
    await update.message.reply_text(
        f"💰 *Твой баланс:* {total} ₽\n📈 Доходы: {income} ₽\n📉 Расходы: {expense} ₽",
        parse_mode='Markdown'
    )

async def add_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'user_id' not in context.user_data:
        await update.message.reply_text("Сначала используй /start")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Формат: /income сумма описание\nПример: /income 5000 зарплата")
        return
    try:
        amount = float(args[0])
        description = " ".join(args[1:])
        user_id = context.user_data['user_id']
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO transactions (user_id, amount, description, type, category, date) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, amount, description, 'income', 'telegram', datetime.now().date())
        )
        conn.commit()
        cur.close()
        conn.close()
        await update.message.reply_text(f"✅ Доход {amount}₽ на '{description}' записан.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'user_id' not in context.user_data:
        await update.message.reply_text("Сначала используй /start")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Формат: /expense сумма описание\nПример: /expense 300 такси")
        return
    try:
        amount = float(args[0])
        description = " ".join(args[1:])
        user_id = context.user_data['user_id']
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO transactions (user_id, amount, description, type, category, date) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, amount, description, 'expense', 'telegram', datetime.now().date())
        )
        conn.commit()
        cur.close()
        conn.close()
        await update.message.reply_text(f"✅ Расход {amount}₽ на '{description}' записан.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def link_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Привязывает Telegram-аккаунт к существующему пользователю веб-трекера"""
    args = context.args
    if len(args) != 2:
        await update.message.reply_text(
            "❌ Формат: /link username пароль\n"
            "Используй те же имя пользователя и пароль, что и при регистрации на сайте."
        )
        return
    username = args[0]
    password = args[1]
    
    conn = get_db_connection()
    cur = conn.cursor()
    # Проверяем пользователя по username и паролю
    cur.execute("SELECT id, password_hash FROM users WHERE username = %s", (username,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        await update.message.reply_text("❌ Пользователь не найден. Зарегистрируйся сначала на сайте.")
        return
    user_id, password_hash = row
    if not check_password_hash(password_hash, password):
        cur.close()
        conn.close()
        await update.message.reply_text("❌ Неверный пароль.")
        return
    # Привязываем telegram_id к этому пользователю
    telegram_id = update.effective_user.id
    cur.execute("UPDATE users SET telegram_id = %s WHERE id = %s", (telegram_id, user_id))
    conn.commit()
    cur.close()
    conn.close()
    
    context.user_data['user_id'] = user_id
    await update.message.reply_text(
        f"✅ Аккаунт {username} успешно привязан к Telegram!\n"
        "Теперь бот и сайт показывают одни и те же транзакции."
    )

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отвязывает Telegram-аккаунт от пользователя и очищает сессию"""
    telegram_id = update.effective_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    # Удаляем привязку telegram_id в БД
    cur.execute("UPDATE users SET telegram_id = NULL WHERE telegram_id = %s", (telegram_id,))
    conn.commit()
    cur.close()
    conn.close()
    # Очищаем данные в памяти бота
    if 'user_id' in context.user_data:
        del context.user_data['user_id']
    await update.message.reply_text(
        "✅ Вы вышли из аккаунта. Чтобы снова привязать бота, используйте /link или /start."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'user_id' not in context.user_data:
        await update.message.reply_text("Сначала используй /start")
        return
    text = update.message.text.strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 2 and parts[0].replace('.', '', 1).isdigit():
        amount = float(parts[0])
        description = parts[1]
        user_id = context.user_data['user_id']
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO transactions (user_id, amount, description, type, category, date) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, amount, description, 'expense', 'telegram', datetime.now().date())
        )
        conn.commit()
        cur.close()
        conn.close()
        await update.message.reply_text(f"✅ Расход {amount}₽ на '{description}' записан.")
    else:
        await update.message.reply_text(
            "❌ Не понял формат.\n"
            "Чтобы добавить расход, напиши: *сумма описание*\n"
            "Пример: `300 такси`\n"
            "Или используй команды /income или /expense.",
            parse_mode='Markdown'
        )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('balance', balance))
    app.add_handler(CommandHandler('income', add_income))
    app.add_handler(CommandHandler('expense', add_expense))
    app.add_handler(CommandHandler('link', link_account))
    app.add_handler(CommandHandler('logout', logout))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Бот запущен. Начинаем polling...")
    app.run_polling()

if __name__ == '__main__':
    main()
