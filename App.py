from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy 
from sqlalchemy import distinct, func, text  # ← ДОБАВИЛ text
from werkzeug.security import generate_password_hash, check_password_hash
import os
import re
import secrets
import time

# --- Конфигурация ---
app = Flask(__name__)

# АВТОМАТИЧЕСКОЕ ИСПРАВЛЕНИЕ ДЛЯ RAILWAY
if os.environ.get('RAILWAY_ENVIRONMENT'):
    # 🚀 НА RAILWAY (продакшен)
    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key:
        secret_key = 'railway-fallback-secret-key-2024-' + secrets.token_hex(16)
        print("⚠️  SECRET_KEY не найден! Используем автоматический ключ")
    app.config['SECRET_KEY'] = secret_key
    
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        print("🚀 Используем PostgreSQL базу")
    else:
        # ФИКС: Создаем правильный путь для SQLite
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.getcwd(), 'railway_production.db')
        print("⚠️  DATABASE_URL не найден! Используем SQLite")
    
    DEBUG_MODE = False
    print("🚀 Запуск в ПРОДАКШЕН режиме (Railway)")
else:
    # 💻 Локальная разработка  
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production-12345'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.getcwd(), 'gamespecial.db')
    DEBUG_MODE = True
    print("💻 Запуск в РАЗРАБОТКЕ (локально)")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация базы данных
db = SQLAlchemy(app)

# --- Модели (без изменений) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), default='') 
    contact = db.Column(db.String(100), default='')
    discord = db.Column(db.String(100), default='')
    telegram = db.Column(db.String(100), default='')
    preferred_role = db.Column(db.String(100), default='') 
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=func.now())
    
    games = db.relationship('Game', backref='player', lazy='dynamic', cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_title = db.Column(db.String(120), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=func.now())
    is_read = db.Column(db.Boolean, default=False)
    
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')

# --- ДОСТУПНЫЕ ИГРЫ ---
AVAILABLE_GAMES = [
    "World of Warcraft", "Cyberpunk 2077", "Dota 2", "Counter-Strike 2", 
    "Baldur's Gate 3", "Minecraft", "Apex Legends", "Genshin Impact", "Rocket League"
]

# --- Валидаторы ---
def validate_username(username):
    if len(username) < 3: return "Имя пользователя должно быть не менее 3 символов"
    if len(username) > 20: return "Имя пользователя должно быть не более 20 символов"
    if not re.match(r'^[a-zA-Z0-9_]+$', username): return "Только латинские буквы, цифры и _"
    return None

def validate_email(email):
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return "Некорректный формат email"
    return None

def validate_password(password):
    if len(password) < 6: return "Пароль должен быть не менее 6 символов"
    return None

# --- Декораторы безопасности ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def ownership_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'error')
            return redirect(url_for('login'))
        username = kwargs.get('username')
        user = User.query.filter_by(username=username).first_or_404()
        if user.id != session.get('user_id'):
            flash('У вас нет прав для этого действия', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# --- АДМИН СИСТЕМА ---
ADMIN_USERNAMES = ['MollNik']

def is_admin():
    return session.get('username') in ADMIN_USERNAMES

# --- Инициализация базы данных ---
def init_db():
    """Инициализирует базу данных"""
    max_retries = 5
    for attempt in range(max_retries):
        try:
            with app.app_context():
                print(f"🔄 Попытка создания таблиц ({attempt + 1}/{max_retries})...")
                db.create_all()
                
                # Проверяем, что таблицы создались
                db.session.execute(text('SELECT 1 FROM user LIMIT 1'))
                print("✅ База данных инициализирована успешно!")
                return True
                
        except Exception as e:
            print(f"⚠️  Попытка {attempt + 1} не удалась: {str(e)}")
            if "no such table" in str(e):
                print("🔄 Создаем таблицы...")
                db.create_all()
                db.session.commit()
                print("✅ Таблицы созданы!")
                return True
            elif attempt < max_retries - 1:
                wait_time = 2 * (attempt + 1)
                print(f"⏳ Ждем {wait_time} секунд перед повторной попыткой...")
                time.sleep(wait_time)
            else:
                print("❌ Не удалось инициализировать базу данных после всех попыток")
                return False

# --- ОСНОВНЫЕ МАРШРУТЫ ---
@app.route('/')
def home():
    try:
        user_count = User.query.filter_by(is_active=True).count()
        game_count = db.session.query(func.count(distinct(Game.game_title))).scalar()
        users = User.query.filter_by(is_active=True).order_by(User.created_at.desc()).limit(20).all()
        
        return render_template('home.html', users=users, user_count=user_count, games_in_db=game_count)
    except Exception as e:
        # Если таблиц нет, показываем пустую страницу
        return render_template('home.html', users=[], user_count=0, games_in_db=0)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            
            user = User.query.filter_by(username=username, is_active=True).first()
            
            if user and user.check_password(password):
                session['user_id'] = user.id
                session['username'] = user.username
                flash(f'Добро пожаловать, {user.username}!', 'success')
                
                if is_admin():
                    flash('👑 Вы вошли как администратор!', 'success')
                
                return redirect(url_for('home'))
            else:
                flash('Неверное имя пользователя или пароль', 'error')
        except Exception as e:
            flash('Ошибка базы данных. Попробуйте позже.', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            # Очищаем email от неактивных пользователей
            inactive_user = User.query.filter_by(email=email, is_active=False).first()
            if inactive_user:
                db.session.delete(inactive_user)
                db.session.commit()
                flash('Старый аккаунт с этим email был удален. Можете регистрироваться заново.', 'info')
            
            if error := validate_username(username):
                flash(error, 'error')
            elif error := validate_email(email):
                flash(error, 'error')
            elif error := validate_password(password):
                flash(error, 'error')
            elif password != confirm_password:
                flash('Пароли не совпадают', 'error')
            elif User.query.filter_by(username=username).first():
                flash('❌ Пользователь с таким именем уже существует!', 'error')
            elif User.query.filter_by(email=email).first():
                flash('❌ Пользователь с таком email уже существует!', 'error')
            else:
                user = User(username=username, email=email)
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                
                flash('✅ Регистрация успешна! Теперь войдите в систему.', 'success')
                
                if username in ADMIN_USERNAMES:
                    flash('👑 Вы зарегистрировались как администратор!', 'success')
                
                return redirect(url_for('login'))
        except Exception as e:
            flash(f'Ошибка при регистрации. Попробуйте позже.', 'error')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('home'))

@app.route('/profile/<username>')
def view_profile(username):
    try:
        user = User.query.filter_by(username=username, is_active=True).first_or_404()
        return render_template('profile.html', user=user)
    except Exception as e:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('home'))

# --- ДИАГНОСТИКА ---
@app.route('/debug')
def debug():
    try:
        # Пытаемся получить данные из БД
        user_count = User.query.count()
        total_games = Game.query.count()
        db_status = "connected"
    except Exception as e:
        user_count = 0
        total_games = 0
        db_status = f"error: {str(e)}"
    
    info = {
        'RAILWAY_ENVIRONMENT': os.environ.get('RAILWAY_ENVIRONMENT'),
        'DATABASE_URL': 'ЕСТЬ' if os.environ.get('DATABASE_URL') else 'НЕТ',
        'SECRET_KEY': 'ЕСТЬ' if os.environ.get('SECRET_KEY') else 'НЕТ (авто)',
        'total_users': user_count,
        'total_games': total_games,
        'database_status': db_status
    }
    return jsonify(info)

@app.route('/test_db')
def test_db():
    """Простой тест подключения к БД"""
    try:
        # ФИКС: Используем text() для SQL выражений
        db.session.execute(text('SELECT 1'))
        user_count = User.query.count()
        return jsonify({
            'status': 'success',
            'message': 'База данных подключена',
            'user_count': user_count,
            'database_type': 'PostgreSQL' if os.environ.get('DATABASE_URL') else 'SQLite'
        })
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': f'Ошибка БД: {str(e)}',
            'database_type': 'PostgreSQL' if os.environ.get('DATABASE_URL') else 'SQLite'
        }), 500

# --- ЗАПУСК ПРИЛОЖЕНИЯ ---
if __name__ == '__main__':
    # Инициализируем базу данных
    print("🚀 Запуск инициализации базы данных...")
    db_initialized = init_db()
    
    if db_initialized:
        print("✅ Приложение готово к работе!")
    else:
        print("⚠️  Приложение запускается с ограниченной функциональностью")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=DEBUG_MODE)