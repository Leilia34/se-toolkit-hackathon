from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)

# Путь к базе данных
DATABASE = 'transactions.db'

def get_db():
    """Возвращает соединение с БД"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Создаёт таблицу, если её нет"""
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                description TEXT NOT NULL,
                type TEXT CHECK(type IN ('income', 'expense')) NOT NULL,
                date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')

@app.route('/')
def index():
    """Главная страница: показывает все транзакции и баланс"""
    db = get_db()
    transactions = db.execute('SELECT * FROM transactions ORDER BY date DESC').fetchall()
    
    # Расчёт баланса: сумма доходов минус расходы
    balance = 0
    for t in transactions:
        if t['type'] == 'income':
            balance += t['amount']
        else:
            balance -= t['amount']
    
    return render_template('index.html', transactions=transactions, balance=balance)

@app.route('/add', methods=['POST'])
def add_transaction():
    """Добавляет новую транзакцию"""
    amount = float(request.form['amount'])
    description = request.form['description']
    trans_type = request.form['type']
    
    db = get_db()
    db.execute(
        'INSERT INTO transactions (amount, description, type) VALUES (?, ?, ?)',
        (amount, description, trans_type)
    )
    db.commit()
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
