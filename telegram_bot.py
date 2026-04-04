import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import psycopg2
import os
from datetime import datetime

BOT_TOKEN = "8660176046:AAFgh3bPfUtm8EINKtqxSZOLXs5x2iOV6Iw"

def get_db_connection():
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://tracker:tracker123@db:5432/expenses')
    return psycopg2.connect(DATABASE_URL)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌟 Привет! Я твой финансовый помощник.\n"
        "Используй /help, чтобы узнать, что я умею."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 *Доступные команды:*\n\n"
        "/start — Приветствие\n"
        "/help  — Показать это сообщение\n"
        "/balance — Текущий баланс (доходы - расходы)\n\n"
        "💰 *Добавить расход:*\n"
        "Просто напиши сумму и описание.\n"
        "Пример: `300 такси`\n\n"
        "📈 *Доходы* пока добавляй через веб-версию трекера.\n"
        "Скоро добавлю и сюда.\n\n"
        "🌐 Веб-трекер: http://10.93.26.99:5002 (доступен через VPN/туннель)"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='income'")
    income = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='expense'")
    expense = cur.fetchone()[0]
    total = income - expense
    cur.close()
    conn.close()
    await update.message.reply_text(
        f"💰 *Текущий баланс:* {total} ₽\n"
        f"📈 Доходы: {income} ₽\n"
        f"📉 Расходы: {expense} ₽",
        parse_mode='Markdown'
    )

async def income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "❌ Формат: /income сумма описание\n"
                "Пример: /income 5000 зарплата"
            )
            return
        amount = float(args[0])
        description = " ".join(args[1:])
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO transactions (amount, description, type, category, date) VALUES (%s, %s, %s, %s, %s)",
            (amount, description, 'income', 'telegram', datetime.now().date())
        )
        conn.commit()
        cur.close()
        conn.close()
        await update.message.reply_text(f"✅ Доход {amount}₽ на '{description}' записан.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 2 and parts[0].replace('.', '', 1).isdigit():
        amount = float(parts[0])
        description = parts[1]
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO transactions (amount, description, type, category, date) VALUES (%s, %s, %s, %s, %s)",
            (amount, description, 'expense', 'telegram', datetime.now().date())
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
            "Или отправь /help для списка команд.",
            parse_mode='Markdown'
        )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('balance', balance))
    app.add_handler(CommandHandler('income', income))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Бот запущен. Начинаем polling...")
    app.run_polling()

if __name__ == '__main__':
    main()
