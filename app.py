from flask import Flask, render_template, request, redirect, url_for, session, flash
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import pandas as pd
import io
from flask import send_file
import numpy as np
import pickle
import datetime
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

# Load ML model
model = pickle.load(open("models/expense_predictor_model.pkl","rb"))
financial_model = pickle.load(open("models/custom_predictor_model.pkl","rb"))

# Get database connection
def get_db_connection():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

# Initialize databases
def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS saved_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            income REAL,
            age INTEGER,
            dependents INTEGER,
            occupation TEXT,
            city_tier INTEGER,
            total_expenses REAL,
            balance REAL,
            predicted_expense REAL,
            predicted_financial_score REAL,
            date TEXT,
            month TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS feedbacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            admin_reply TEXT
        )
    ''')
    

    conn.commit()
    conn.close()

def add_column_if_not_exists():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    try:
        cursor.execute("ADD COLUMN predicted_financial_score REAL;")
        conn.commit()
        print("Column added successfully.")
    except sqlite3.OperationalError:
        # This error occurs if column already exists, so we can ignore it
        print("Column already exists or another error.")
    finally:
        conn.close()

init_db()

@app.route('/')
def home():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    elif session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('login'))

# ======== USER ROUTES ========

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = generate_password_hash(request.form['password'])

        conn = get_db_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "User already exists."
        conn.close()
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password_input = request.form.get('password')

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password_input):
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            return "Invalid credentials."

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('admin_logged_in', None)
    return redirect(url_for('login'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            income = float(request.form.get('income', 0))
            age = int(request.form.get('age', 0))
            dependents = int(request.form.get('dependents', 0))
            occupation = int(request.form.get('occupation', 0))
            city_tier = int(request.form.get('city_tier', 0))
            if city_tier not in [1, 2, 3]:
                return "Invalid City Tier. Must be 1, 2, or 3.", 400

            labels = [v for k, v in request.form.items() if k.startswith("label_")]
            expenses = [float(v) for k, v in request.form.items() if k.startswith("expense_") and v]

            total_expense = sum(expenses)
            balance = income - total_expense
            warning = None

            if balance < 0:
                balance = 0
                warning = "⚠️ Warning: Your total expenses exceed your income. Balance is set to ₹0."

            features = [[income, age, dependents, occupation, city_tier]]
            predicted_expense = model.predict(features)[0]

             # New: Inputs for financial score prediction
            Disposable_income = float(request.form.get('Disposable_income', 0))
            Desired_savings = float(request.form.get('Desired_savings', 0))  
            Loan_repayment= float(request.form.get('Loan_repayment', 0))

            financial_features = [[income, Disposable_income, Desired_savings, Loan_repayment]]
            predicted_financial_score = financial_model.predict(financial_features)[0]

          
           
            current_date = datetime.date.today().strftime("%Y-%m-%d")
            month = datetime.date.today().strftime("%B")
            actual_expense = total_expense
            predicted_expense = predicted_expense

            return render_template('result.html',
                                   date=current_date,
                                   month=month,
                                   income=income,
                                   total=total_expense,
                                   balance=balance,
                                   predicted=predicted_expense,
                                   predicted_financial_score=round(predicted_financial_score, 2),
                                   actual_expense=actual_expense,
                                   predicted_expense=predicted_expense,
                                   labels=labels,
                                   values=expenses,
                                   age=age,
                                   dependents=dependents,
                                   occupation=occupation,
                                   city_tier=city_tier,
                                   warning=warning)
        except Exception as e:
            return f"Error: {e}"

    return render_template('form_dynamic.html')

@app.route('/predict', methods=['POST'])
def predict_():
    Income=float(request.form['Income'])
    disposable_income = float(request.form['Disposable_income'])
    desired_savings = float(request.form['Desired_savings'])
    loan_repayment = float(request.form['Loan_repayment'])

    # Load your model and predict here
    prediction = model.predict([[Income,disposable_income, desired_savings, loan_repayment]])
    predicted_financial_score = round(prediction[0], 2) 
    return render_template('result.html', predicted_financial_score=predicted_financial_score)

@app.route('/result')
def result():
    labels = ['Rent', 'Groceries', 'Transport', 'Healthcare', 'Entertainment']
    values = [12000, 4500, 2300, 1100, 3400]
    return render_template('result.html', labels=labels, values=values)



@app.route('/save', methods=['POST'])
def save():
    if 'username' not in session:
        return redirect(url_for('login'))

    try:
        username = session['username']
        income = float(request.form['income'])
        age = int(request.form['age'])
        dependents = int(request.form['dependents'])
        occupation = int(request.form['occupation'])
        city_tier = int(request.form['city_tier'])
        total_expenses = float(request.form['total_expenses'])
        balance = float(request.form['balance'])
        predicted_expense = float(request.form['predicted_expense'])
        predicted_financial_score = float(request.form['predicted_financial_score'])
        date = datetime.date.today().strftime("%Y-%m-%d")
        month = datetime.date.today().strftime("%B")

        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO saved_expenses (username, income, age, dependents, occupation, city_tier,
                                        total_expenses, balance, predicted_expense,predicted_financial_score, date, month)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,?)
        ''', (username, income, age, dependents, occupation, city_tier,
              total_expenses, balance, predicted_expense,predicted_financial_score, date, month))
        conn.commit()
        conn.close()

        return "✅ Data saved successfully! <br><br><a href='/dashboard'>← Back to Dashboard</a>"
    except Exception as e:
        return f"Error while saving data: {e}"

@app.route('/history')
def history():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, date, month, income, total_expenses, balance, 
               predicted_expense, predicted_financial_score
        FROM saved_expenses
        WHERE username = ?
        ORDER BY date DESC
    """, (username,))
    records = c.fetchall()
    conn.close()

    return render_template('history.html', records=records)


@app.route('/delete/<int:record_id>', methods=['POST'])
def delete_record(record_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM saved_expenses WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('history'))

@app.route('/delete_account', methods=['GET', 'POST'])
def delete_account():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = session['username']

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM saved_expenses WHERE username = ?", (username,))
        c.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
        conn.close()

        session.pop('username', None)
        return "🗑️ Your account has been deleted successfully.<br><br><a href='/signup'>Sign Up Again</a>"

    return render_template('delete_account.html')

# ====== FEEDBACK FEATURE ======

@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if request.method == 'POST':
        name = request.form.get('name', '').strip() or None
        email = request.form.get('email', '').strip() or None
        message = request.form.get('message', '').strip()

        if not message:
            return "Message is required."

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO feedbacks (name, email, message, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (name, email, message, timestamp))
        conn.commit()
        conn.close()

        return "✅ Thank you for your feedback!<br><br><a href='/feedback'>Leave more feedback</a> | <a href='/'>Home</a>"

    return render_template('feedback.html')

@app.route('/feedbacks')
def feedbacks():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        SELECT 
            message, 
            timestamp, 
            CASE WHEN name IS NULL OR name = '' THEN 'Anonymous' ELSE name END AS display_name,
            reply
        FROM feedbacks
        ORDER BY timestamp DESC
        LIMIT 10
    ''')
    feedback_list = c.fetchall()
    conn.close()

    return render_template('feedbacks.html', feedbacks=feedback_list)

@app.route('/view_feedbacks')
def view_feedbacks():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT username, feedback, reply, timestamp FROM feedbacks ORDER BY timestamp DESC")
    feedbacks = c.fetchall()
    conn.close()
    return render_template('feedbacks.html', feedbacks=feedbacks)


# ======= ADMIN ROUTES =======

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return "Invalid Admin Credentials"
    return render_template('admin_login.html')

@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM feedbacks ORDER BY timestamp DESC")
    feedbacks = c.fetchall()
    conn.close()

    return render_template('admin_dashboard.html', feedbacks=feedbacks)

@app.route('/admin_reply', methods=['POST'])
def admin_reply():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    feedback_id = request.form['feedback_id']
    reply_text = request.form['reply']

    conn =sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE feedbacks SET reply = ? WHERE id = ?", (reply_text, feedback_id))
    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/delete_feedback', methods=['POST'])
def delete_feedback():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    feedback_id = request.form['feedback_id']

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('DELETE FROM feedbacks WHERE id = ?', (feedback_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)  # Remove admin session (adjust based on your session key)
    return redirect(url_for('admin_login'))  # Redirect to admin login page


if __name__ == '__main__':
    app.run(debug=True)
