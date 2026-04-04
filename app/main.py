import os
import time
from flask import Flask, render_template, request, redirect, url_for
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import OperationalError

app = Flask(__name__)

def get_db_connection():
    conn = psycopg2.connect(
        os.environ.get('DATABASE_URL', 'postgresql://tracker:tracker123@db:5432/expenses')
    )
    return conn

def init_db(retries=5, delay=3):
    for i in range(retries):
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id SERIAL PRIMARY KEY,
                        amount REAL NOT NULL,
                        description TEXT NOT NULL,
                        type TEXT CHECK(type IN ('income', 'expense')) NOT NULL,
                        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
            conn.close()
            print("Database initialized successfully")
            return
        except OperationalError as e:
            print(f"Database not ready (attempt {i+1}/{retries}): {e}")
            time.sleep(delay)
    raise Exception("Could not initialize database after retries")

@app.route('/')
def index():
    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT * FROM transactions ORDER BY date DESC')
        transactions = cur.fetchall()
    
    balance = 0
    for t in transactions:
        if t['type'] == 'income':
            balance += t['amount']
        else:
            balance -= t['amount']
    conn.close()
    return render_template('index.html', transactions=transactions, balance=balance)

@app.route('/add', methods=['POST'])
def add_transaction():
    amount = float(request.form['amount'])
    description = request.form['description']
    trans_type = request.form['type']
    
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO transactions (amount, description, type) VALUES (%s, %s, %s)',
            (amount, description, trans_type)
        )
        conn.commit()
    conn.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
