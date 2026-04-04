import os
import time
import csv
from io import StringIO
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, Response, session, flash
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import OperationalError
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-me')

def get_db_connection():
    return psycopg2.connect(
        os.environ.get('DATABASE_URL', 'postgresql://tracker:tracker123@db:5432/expenses')
    )

def init_db(retries=5, delay=3):
    for i in range(retries):
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(50) UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        telegram_id BIGINT UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        amount REAL NOT NULL,
                        description TEXT NOT NULL,
                        type TEXT CHECK(type IN ('income', 'expense')) NOT NULL,
                        category VARCHAR(50) DEFAULT 'other',
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

def get_default_dates():
    today = datetime.now().date()
    end_date = today
    start_date = today - timedelta(days=30)
    return start_date.isoformat(), end_date.isoformat()

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    trans_type = request.args.get('type', '')
    category_filter = request.args.get('category', '')
    
    default_start, default_end = get_default_dates()
    if not start_date:
        start_date = default_start
    if not end_date:
        end_date = default_end
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    query = 'SELECT * FROM transactions WHERE user_id = %s AND date >= %s AND date <= %s'
    params = [session['user_id'], start_date, end_date + ' 23:59:59']
    
    if trans_type:
        query += ' AND type = %s'
        params.append(trans_type)
    if category_filter:
        query += ' AND category = %s'
        params.append(category_filter)
    
    query += ' ORDER BY date DESC'
    cursor.execute(query, params)
    transactions = cursor.fetchall()
    
    balance = 0
    for t in transactions:
        if t['type'] == 'income':
            balance += t['amount']
        else:
            balance -= t['amount']
    
    conn.close()
    
    return render_template('index.html',
                           transactions=transactions,
                           balance=balance,
                           start_date=start_date,
                           end_date=end_date,
                           selected_type=trans_type,
                           selected_category=category_filter,
                           today=datetime.now().date().isoformat())

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if not username or not password:
            flash('Username and password required')
            return redirect(url_for('register'))
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute('INSERT INTO users (username, password_hash) VALUES (%s, %s)',
                       (username, generate_password_hash(password)))
            conn.commit()
            flash('Registration successful. Please log in.')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Username already exists')
        finally:
            cur.close()
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/add', methods=['POST'])
def add_transaction():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    amount = float(request.form['amount'])
    description = request.form['description']
    trans_type = request.form['type']
    category = request.form['category']
    transaction_date = request.form.get('date', datetime.now().date().isoformat())
    
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO transactions (user_id, amount, description, type, category, date) VALUES (%s, %s, %s, %s, %s, %s)',
            (session['user_id'], amount, description, trans_type, category, transaction_date)
        )
        conn.commit()
    conn.close()
    return redirect(url_for('index', **{k: v for k, v in request.args.items() if k in ['start_date', 'end_date', 'type', 'category']}))

@app.route('/delete/<int:id>')
def delete_transaction(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute('DELETE FROM transactions WHERE id = %s AND user_id = %s', (id, session['user_id']))
        conn.commit()
    conn.close()
    return redirect(url_for('index', **request.args))

@app.route('/export/csv')
def export_csv():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    trans_type = request.args.get('type', '')
    category_filter = request.args.get('category', '')
    
    if not start_date or not end_date:
        default_start, default_end = get_default_dates()
        start_date = start_date or default_start
        end_date = end_date or default_end
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    query = 'SELECT * FROM transactions WHERE user_id = %s AND date >= %s AND date <= %s'
    params = [session['user_id'], start_date, end_date + ' 23:59:59']
    if trans_type:
        query += ' AND type = %s'
        params.append(trans_type)
    if category_filter:
        query += ' AND category = %s'
        params.append(category_filter)
    query += ' ORDER BY date DESC'
    cursor.execute(query, params)
    transactions = cursor.fetchall()
    conn.close()
    
    si = StringIO()
    si.write('\ufeff')
    writer = csv.writer(si, delimiter=';')
    writer.writerow(['ID', 'Сумма', 'Описание', 'Тип', 'Категория', 'Дата'])
    for t in transactions:
        date_str = t['date'].strftime('%d.%m.%Y %H:%M') if isinstance(t['date'], datetime) else str(t['date'])
        writer.writerow([t['id'], t['amount'], t['description'],
                         'Доход' if t['type'] == 'income' else 'Расход',
                         t['category'], date_str])
    output = si.getvalue()
    return Response(output, mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=transactions.csv'})

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
