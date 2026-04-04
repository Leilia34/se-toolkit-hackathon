import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import psycopg2
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

BOT_TOKEN = "8660176046:AAFgh3bPfUtm8EINKtqxSZOLXs5x2iOV6Iw"

def get_db_connection():
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://tracker:tracker123@localhost:5432/expenses')
    return psycopg2.connect(DATABASE_URL)

# Инициализация таблиц (если нет)
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            telegram_id BIGINT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, name)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            wallet_id INTEGER NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
            amount REAL NOT NULL,
            description TEXT NOT NULL,
            type TEXT CHECK(type IN ('income', 'expense')) NOT NULL,
            category VARCHAR(50) DEFAULT 'other',
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

def get_or_create_user(telegram_id, username=None):
    conn = get_db_connection()
    cur = conn.cursor()
    # Сначала ищем по telegram_id
    cur.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
    row = cur.fetchone()
    if row:
        user_id = row[0]
        cur.close()
        conn.close()
        return user_id
    # Если есть username, пробуем найти по нему
    if username:
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        if row:
            user_id = row[0]
            # Привязываем telegram_id к существующему пользователю
            cur.execute("UPDATE users SET telegram_id = %s WHERE id = %s", (telegram_id, user_id))
            conn.commit()
            cur.close()
            conn.close()
            return user_id
    # Создаём нового пользователя
    if not username:
        username = f"tg_{telegram_id}"
    import secrets
    password = secrets.token_urlsafe(12)
    password_hash = generate_password_hash(password)
    # Пытаемся создать, если username занят, добавляем суффикс
    for suffix in ['', f"_{int(datetime.now().timestamp())}"]:
        try:
            final_username = username + suffix
            cur.execute(
                "INSERT INTO users (username, password_hash, telegram_id) VALUES (%s, %s, %s) RETURNING id",
                (final_username, password_hash, telegram_id)
            )
            user_id = cur.fetchone()[0]
            conn.commit()
            # Создаём кошелёк по умолчанию
            cur.execute("INSERT INTO wallets (user_id, name) VALUES (%s, %s)", (user_id, 'Личный'))
            conn.commit()
            cur.close()
            conn.close()
            return user_id
        except Exception:
            continue
    raise Exception("Could not create user")
def get_current_wallet(telegram_id):
    """Возвращает wallet_id, который пользователь выбрал последним (хранится в БД или в context). Упростим: пока в памяти бота."""
    # Здесь можно хранить в таблице user_settings, но для простоты используем глобальный словарь
    if not hasattr(get_current_wallet, 'cache'):
        get_current_wallet.cache = {}
    cache = get_current_wallet.cache
    if telegram_id not in cache:
        # Находим первый кошелёк пользователя
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT w.id FROM wallets w
            JOIN users u ON u.id = w.user_id
            WHERE u.telegram_id = %s LIMIT 1
        """, (telegram_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            cache[telegram_id] = row[0]
        else:
            return None
    return cache[telegram_id]

def set_current_wallet(telegram_id, wallet_id):
    if not hasattr(get_current_wallet, 'cache'):
        get_current_wallet.cache = {}
    get_current_wallet.cache[telegram_id] = wallet_id

async def wallets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT w.id, w.name FROM wallets w
        JOIN users u ON u.id = w.user_id
        WHERE u.telegram_id = %s
    """, (telegram_id,))
    wallets = cur.fetchall()
    cur.close()
    conn.close()
    if not wallets:
        await update.message.reply_text("У вас нет кошельков. Создайте первый командой /create_wallet <название>")
        return
    text = "Ваши кошельки:\n"
    keyboard = []
    for wid, name in wallets:
        text += f"• {name}\n"
        keyboard.append([InlineKeyboardButton(name, callback_data=f"switch_{wid}")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def switch_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    wallet_id = int(query.data.split('_')[1])
    telegram_id = query.from_user.id
    set_current_wallet(telegram_id, wallet_id)
    await query.edit_message_text(f"✅ Переключено на кошелёк {query.data.split('_')[1]}")

async def create_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("❌ Используй: /create_wallet <название>")
        return
    name = args[0]
    telegram_id = update.effective_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
    user = cur.fetchone()
    if not user:
        await update.message.reply_text("Сначала используй /start")
        cur.close()
        conn.close()
        return
    user_id = user[0]
    try:
        cur.execute("INSERT INTO wallets (user_id, name) VALUES (%s, %s)", (user_id, name))
        conn.commit()
        await update.message.reply_text(f"✅ Кошелёк '{name}' создан. Используй /wallets для переключения.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: возможно, кошелёк с таким именем уже существует.")
    finally:
        cur.close()
        conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    user_id = get_or_create_user(telegram_id, update.effective_user.username)
    # Устанавливаем кошелёк по умолчанию (первый)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM wallets WHERE user_id = %s ORDER BY id LIMIT 1", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        set_current_wallet(telegram_id, row[0])
    await update.message.reply_text(
        "🌟 Добро пожаловать в многокошелёчный финансовый трекер!\n"
        "Команды:\n/wallets — показать кошельки\n/create_wallet <название> — создать новый\n"
        "/balance — баланс текущего кошелька\n/income сумма описание — доход\n/expense сумма описание — расход\n"
        "Просто сумма описание — расход\n/link username пароль — привязать к веб-аккаунту\n/logout — отвязать\n/help — помощь"
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    wallet_id = get_current_wallet(telegram_id)
    if not wallet_id:
        await update.message.reply_text("Сначала создайте кошелёк (/create_wallet) или выберите /wallets")
        return
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE wallet_id=%s AND type='income'", (wallet_id,))
    income = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE wallet_id=%s AND type='expense'", (wallet_id,))
    expense = cur.fetchone()[0]
    total = income - expense
    cur.close()
    conn.close()
    await update.message.reply_text(f"💰 Баланс: {total} ₽\n📈 Доходы: {income} ₽\n📉 Расходы: {expense} ₽")

async def add_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    wallet_id = get_current_wallet(telegram_id)
    if not wallet_id:
        await update.message.reply_text("Сначала создайте кошелёк (/create_wallet)")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Формат: /income сумма описание")
        return
    amount = float(args[0])
    description = " ".join(args[1:])
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO transactions (wallet_id, amount, description, type, category, date) VALUES (%s, %s, %s, %s, %s, %s)",
                (wallet_id, amount, description, 'income', 'telegram', datetime.now().date()))
    conn.commit()
    cur.close()
    conn.close()
    await update.message.reply_text(f"✅ Доход {amount}₽ на '{description}' записан.")

async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    wallet_id = get_current_wallet(telegram_id)
    if not wallet_id:
        await update.message.reply_text("Сначала создайте кошелёк (/create_wallet)")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Формат: /expense сумма описание")
        return
    amount = float(args[0])
    description = " ".join(args[1:])
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO transactions (wallet_id, amount, description, type, category, date) VALUES (%s, %s, %s, %s, %s, %s)",
                (wallet_id, amount, description, 'expense', 'telegram', datetime.now().date()))
    conn.commit()
    cur.close()
    conn.close()
    await update.message.reply_text(f"✅ Расход {amount}₽ на '{description}' записан.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    wallet_id = get_current_wallet(telegram_id)
    if not wallet_id:
        await update.message.reply_text("Сначала создайте кошелёк (/create_wallet) или выберите /wallets")
        return
    text = update.message.text.strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 2 and parts[0].replace('.', '', 1).isdigit():
        amount = float(parts[0])
        description = parts[1]
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO transactions (wallet_id, amount, description, type, category, date) VALUES (%s, %s, %s, %s, %s, %s)",
                    (wallet_id, amount, description, 'expense', 'telegram', datetime.now().date()))
        conn.commit()
        cur.close()
        conn.close()
        await update.message.reply_text(f"✅ Расход {amount}₽ на '{description}' записан.")
    else:
        await update.message.reply_text("Не понял. Используй /help")

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET telegram_id = NULL WHERE telegram_id = %s", (telegram_id,))
    conn.commit()
    cur.close()
    conn.close()
    if hasattr(get_current_wallet, 'cache') and telegram_id in get_current_wallet.cache:
        del get_current_wallet.cache[telegram_id]
    await update.message.reply_text("✅ Вы вышли. Для входа используйте /start.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *Команды:*\n"
        "/start — начать\n"
        "/wallets — показать кошельки\n"
        "/create_wallet <название> — создать кошелёк\n"
        "/balance — баланс текущего кошелька\n"
        "/income сумма описание — доход\n"
        "/expense сумма описание — расход\n"
        "/link username пароль — привязать к веб-аккаунту (транзакции будут общие)\n"
        "/logout — отвязать Telegram\n"
        "/help — это сообщение",
        parse_mode='Markdown'
    )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('balance', balance))
    app.add_handler(CommandHandler('income', add_income))
    app.add_handler(CommandHandler('expense', add_expense))
    app.add_handler(CommandHandler('wallets', wallets_command))
    app.add_handler(CommandHandler('create_wallet', create_wallet))
    app.add_handler(CommandHandler('logout', logout))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(switch_wallet, pattern='^switch_'))
    print("🤖 Бот с поддержкой нескольких кошельков запущен")
    app.run_polling()

if __name__ == '__main__':
    main()
