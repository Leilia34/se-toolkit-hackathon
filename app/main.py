import os
import time
import csv
from io import StringIO
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, Response
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
    
    query = 'SELECT * FROM transactions WHERE date >= %s AND date <= %s'
    params = [start_date, end_date + ' 23:59:59']
    
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

@app.route('/add', methods=['POST'])
def add_transaction():
    amount = float(request.form['amount'])
    description = request.form['description']
    trans_type = request.form['type']
    category = request.form['category']
    transaction_date = request.form.get('date', datetime.now().date().isoformat())
    
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO transactions (amount, description, type, category, date) VALUES (%s, %s, %s, %s, %s)',
            (amount, description, trans_type, category, transaction_date)
        )
        conn.commit()
    conn.close()
    return redirect(url_for('index', **{k: v for k, v in request.args.items() if k in ['start_date', 'end_date', 'type', 'category']}))

@app.route('/delete/<int:id>')
def delete_transaction(id):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute('DELETE FROM transactions WHERE id = %s', (id,))
        conn.commit()
    conn.close()
    return redirect(url_for('index', **request.args))

@app.route('/export/csv')
def export_csv():
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
    query = 'SELECT * FROM transactions WHERE date >= %s AND date <= %s'
    params = [start_date, end_date + ' 23:59:59']
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
