from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy 
from sqlalchemy import distinct, func 
from werkzeug.security import generate_password_hash, check_password_hash
import os
import re
import secrets

# --- Умная конфигурация ---
app = Flask(__name__)

# АВТООПРЕДЕЛЕНИЕ СРЕДЫ
if os.environ.get('RAILWAY_ENVIRONMENT'):
    # 🚀 НА RAILWAY (продакшен)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    DEBUG_MODE = False
    print("🚀 Запуск в ПРОДАКШЕН режиме (Railway)")
else:
    # 💻 НА ТВОЕМ КОМПЬЮТЕРЕ (разработка)  
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production-12345'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gamespecial.db'
    DEBUG_MODE = True
    print("💻 Запуск в РАЗРАБОТКЕ (локально)")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Доступные игры ---
AVAILABLE_GAMES = [
    "World of Warcraft", "Cyberpunk 2077", "Dota 2", "Counter-Strike 2", 
    "Baldur's Gate 3", "Minecraft", "Apex Legends", "Genshin Impact", "Rocket League"
]

# --- Модели (остаются без изменений) ---
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

# --- Валидаторы (без изменений) ---
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

# --- Декораторы безопасности (без изменений) ---
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

# --- Создание базы данных ---
with app.app_context():
    db.create_all()

# --- ВСЕ маршруты остаются БЕЗ ИЗМЕНЕНИЙ ---
# (копируешь все твои текущие маршруты как есть)

@app.route('/')
def home():
    user_count = User.query.filter_by(is_active=True).count()
    game_count = db.session.query(func.count(distinct(Game.game_title))).scalar()
    
    # Умное ограничение для производительности
    if os.environ.get('RAILWAY_ENVIRONMENT'):
        users = User.query.filter_by(is_active=True).order_by(User.created_at.desc()).limit(20).all()
    else:
        users = User.query.filter_by(is_active=True).all()
    
    return render_template('home.html', users=users, user_count=user_count, games_in_db=game_count)

# ... ВСЕ остальные маршруты (login, register, profile, chat и т.д.)
# КОПИРУЕШЬ ИХ ПОЛНОСТЬЮ БЕЗ ИЗМЕНЕНИЙ ...

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=DEBUG_MODE)