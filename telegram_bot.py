import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import psycopg2
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

BOT_TOKEN = "8660176046:AAFgh3bPfUtm8EINKtqxSZOLXs5x2iOV6Iw"

def get_db_connection():
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://tracker:tracker123@db:5432/expenses')
    return psycopg2.connect(DATABASE_URL)

def get_or_create_user(telegram_id, username=None):
    """Находит пользователя по telegram_id или создаёт нового."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
    row = cur.fetchone()
    if row:
        user_id = row[0]
    else:
        # Создаём нового пользователя
        if not username:
            username = f"tg_{telegram_id}"
        # Генерируем случайный пароль
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

def link_existing_user(telegram_id, username, password):
    """Привязывает telegram_id к существующему пользователю (из веба)."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE username = %s", (username,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return None, "Пользователь не найден"
    user_id, password_hash = row
    if not check_password_hash(password_hash, password):
        cur.close()
        conn.close()
        return None, "Неверный пароль"
    # Обновляем telegram_id (если уже был привязан другой, заменяем)
    cur.execute("UPDATE users SET telegram_id = %s WHERE id = %s", (telegram_id, user_id))
    conn.commit()
    cur.close()
    conn.close()
    return user_id, "Успешно привязано"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    # Всегда создаём или получаем пользователя по telegram_id
    user_id = get_or_create_user(telegram_id, update.effective_user.username)
    context.user_data['user_id'] = user_id
    await update.message.reply_text(
        "🌟 Добро пожаловать в финансовый трекер!\n"
        "Твой аккаунт автоматически создан. Теперь ты можешь:\n"
        "/balance — показать баланс\n"
        "/income сумма описание — добавить доход\n"
        "/expense сумма описание — добавить расход\n"
        "или просто напиши '300 такси' для расхода.\n\n"
        "Если у тебя уже есть аккаунт на сайте, используй /link username пароль, чтобы объединить их."
    )

async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("❌ Формат: /link username пароль")
        return
    username, password = args[0], args[1]
    telegram_id = update.effective_user.id
    user_id, msg = link_existing_user(telegram_id, username, password)
    if user_id:
        context.user_data['user_id'] = user_id
        await update.message.reply_text(f"✅ {msg}. Теперь бот показывает данные с сайта.")
    else:
        await update.message.reply_text(f"❌ {msg}")

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
        f"💰 Баланс: {total} ₽\n📈 Доходы: {income} ₽\n📉 Расходы: {expense} ₽"
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
            "Напиши сумму и описание, например: 300 такси\n"
            "Или используй /income или /expense."
        )

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET telegram_id = NULL WHERE telegram_id = %s", (telegram_id,))
    conn.commit()
    cur.close()
    conn.close()
    if 'user_id' in context.user_data:
        del context.user_data['user_id']
    await update.message.reply_text("✅ Вы вышли. Для входа используйте /start или /link.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 *Команды:*\n\n"
        "/start — создать/войти в свой аккаунт\n"
        "/balance — баланс\n"
        "/income сумма описание — доход\n"
        "/expense сумма описание — расход\n"
        "/link username пароль — привязать к веб-аккаунту\n"
        "/logout — отвязать бота\n"
        "/help — это сообщение\n\n"
        "💰 *Быстрый расход:* просто напиши сумму и описание"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('balance', balance))
    app.add_handler(CommandHandler('income', add_income))
    app.add_handler(CommandHandler('expense', add_expense))
    app.add_handler(CommandHandler('link', link_command))
    app.add_handler(CommandHandler('logout', logout))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Бот запущен")
    app.run_polling()

if __name__ == '__main__':
    main()
