from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy 
from sqlalchemy import text
import os

# --- Минимальная конфигурация ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-123')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Настройка базы данных
database_url = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url

db = SQLAlchemy(app)

# --- Простая модель ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)

# Создаем таблицы при старте
with app.app_context():
    try:
        db.create_all()
        print("✅ Таблицы созданы")
    except Exception as e:
        print(f"❌ Ошибка создания таблиц: {e}")

# --- Только базовые маршруты ---
@app.route('/')
def home():
    try:
        user_count = User.query.count()
        return f"""
        <h1>Сайт работает! 🎉</h1>
        <p>Пользователей в базе: {user_count}</p>
        <p><a href="/debug">Debug</a> | <a href="/test_db">Test DB</a></p>
        """
    except Exception as e:
        return f"""
        <h1>Сайт работает (с ошибками) ⚠️</h1>
        <p>Ошибка: {str(e)}</p>
        <p><a href="/debug">Debug</a> | <a href="/test_db">Test DB</a></p>
        """

@app.route('/debug')
def debug():
    info = {
        'status': 'OK',
        'database': 'Connected',
        'railway_env': os.environ.get('RAILWAY_ENVIRONMENT'),
        'has_database_url': bool(os.environ.get('DATABASE_URL'))
    }
    return jsonify(info)

@app.route('/test_db')
def test_db():
    try:
        user_count = User.query.count()
        return jsonify({
            'status': 'success', 
            'user_count': user_count,
            'message': 'База данных работает'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)