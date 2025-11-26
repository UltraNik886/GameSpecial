from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy 
from sqlalchemy import distinct, func 
from werkzeug.security import generate_password_hash, check_password_hash
import os
import re
import secrets

# --- Конфигурация ---
app = Flask(__name__)

# Автоматическое определение среды с защитой от ошибок
if os.environ.get('RAILWAY_ENVIRONMENT'):
    # 🚀 НА RAILWAY (продакшен)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    
    # ВАЖНО: Проверяем что DATABASE_URL существует
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # Исправляем URL если нужно (для PostgreSQL)
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        DEBUG_MODE = False
        print("🚀 Запуск в ПРОДАКШЕН режиме (Railway)")
    else:
        # Если DATABASE_URL нет - используем SQLite как запасной вариант
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///railway_fallback.db'
        DEBUG_MODE = True
        print("⚠️  DATABASE_URL не найден! Используем SQLite")
else:
    # 💻 НА ТВОЕМ КОМПЬЮТЕРЕ (разработка)  
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production-12345'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gamespecial.db'
    DEBUG_MODE = True
    print("💻 Запуск в РАЗРАБОТКЕ (локально)")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация базы данных с обработкой ошибок
try:
    db = SQLAlchemy(app)
    print("✅ SQLAlchemy инициализирован")
except Exception as e:
    print(f"❌ Ошибка инициализации SQLAlchemy: {e}")
    raise

# --- ДОСТУПНЫЕ ИГРЫ ---
AVAILABLE_GAMES = [
    "World of Warcraft", "Cyberpunk 2077", "Dota 2", "Counter-Strike 2", 
    "Baldur's Gate 3", "Minecraft", "Apex Legends", "Genshin Impact", "Rocket League",
    "League of Legends", "Valorant", "Overwatch 2", "Fortnite", "Call of Duty: Warzone",
    "Escape from Tarkov", "PUBG: Battlegrounds", "Rainbow Six Siege", "Destiny 2"
]

# --- Модели ---
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
ADMIN_USERNAMES = ['MollNik']  # ← ТОЛЬКО ЭТИ ПОЛЬЗОВАТЕЛИ МОГУТ В АДМИНКУ!

def is_admin():
    """Проверяет является ли пользователь админом"""
    return session.get('username') in ADMIN_USERNAMES

# --- АДМИН МАРШРУТЫ ---
@app.route('/admin')
@login_required
def admin_panel():
    """Главная админ панель - ТОЛЬКО ДЛЯ АДМИНОВ!"""
    if not is_admin():
        flash('❌ Доступ запрещен! Только для администраторов.', 'error')
        return redirect(url_for('home'))
    
    try:
        # Статистика
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        total_games = Game.query.count()
        total_messages = Message.query.count()
        
        # Популярные игры
        popular_games = db.session.query(
            Game.game_title, 
            func.count(Game.id).label('count')
        ).group_by(Game.game_title).order_by(func.count(Game.id).desc()).limit(10).all()
        
        # Последние пользователи
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        
        return render_template('admin_panel.html',
                            total_users=total_users,
                            active_users=active_users, 
                            total_games=total_games,
                            total_messages=total_messages,
                            popular_games=popular_games,
                            recent_users=recent_users)
    except Exception as e:
        flash(f'❌ Ошибка загрузки админки: {str(e)}', 'error')
        return redirect(url_for('home'))

# ... остальные админ маршруты с try/except ...

# --- Создание базы данных ---
with app.app_context():
    try:
        db.create_all()
        print("✅ База данных успешно создана/подключена")
    except Exception as e:
        print(f"❌ Ошибка создания базы данных: {e}")

# --- ОСНОВНЫЕ МАРШРУТЫ ---
@app.route('/')
def home():
    try:
        user_count = User.query.filter_by(is_active=True).count()
        game_count = db.session.query(func.count(distinct(Game.game_title))).scalar()
        
        if os.environ.get('RAILWAY_ENVIRONMENT'):
            users = User.query.filter_by(is_active=True).order_by(User.created_at.desc()).limit(20).all()
        else:
            users = User.query.filter_by(is_active=True).all()
        
        return render_template('home.html', users=users, user_count=user_count, games_in_db=game_count)
    except Exception as e:
        print(f"Ошибка в home: {e}")
        return render_template('home.html', users=[], user_count=0, games_in_db=0)

@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            
            print(f"🔐 Попытка входа: {username}")
            
            user = User.query.filter_by(username=username, is_active=True).first()
            
            if user and user.check_password(password):
                session['user_id'] = user.id
                session['username'] = user.username
                flash(f'Добро пожаловать, {user.username}!', 'success')
                
                # Если это админ - покажем сообщение
                if is_admin():
                    flash('👑 Вы вошли как администратор!', 'success')
                
                print(f"✅ Успешный вход: {username}")
                return redirect(url_for('home'))
            else:
                flash('Неверное имя пользователя или пароль', 'error')
                print(f"❌ Ошибка входа: {username}")
        
        return render_template('login.html')
    except Exception as e:
        print(f"❌ Критическая ошибка в login: {e}")
        flash('Внутренняя ошибка сервера. Попробуйте позже.', 'error')
        return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    try:
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            print(f"📝 Попытка регистрации: {username}, {email}")
            
            # Очищаем email от неактивных пользователей
            inactive_user = User.query.filter_by(email=email, is_active=False).first()
            if inactive_user:
                # Полностью удаляем неактивного пользователя с этим email
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
                flash('❌ Пользователь с таким email уже существует!', 'error')
            else:
                user = User(username=username, email=email)
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                
                flash('✅ Регистрация успешна! Теперь войдите в систему.', 'success')
                print(f"✅ Успешная регистрация: {username}")
                
                # Если зарегистрировался админ - особое сообщение
                if username in ADMIN_USERNAMES:
                    flash('👑 Вы зарегистрировались как администратор!', 'success')
                
                return redirect(url_for('login'))
        
        return render_template('register.html')
    except Exception as e:
        print(f"❌ Критическая ошибка в register: {e}")
        flash('Внутренняя ошибка сервера. Попробуйте позже.', 'error')
        return render_template('register.html')

# --- ДИАГНОСТИЧЕСКИЕ МАРШРУТЫ ---
@app.route('/debug')
def debug():
    """Страница диагностики"""
    try:
        info = {
            'RAILWAY_ENVIRONMENT': os.environ.get('RAILWAY_ENVIRONMENT'),
            'DATABASE_URL': 'ЕСТЬ' if os.environ.get('DATABASE_URL') else 'НЕТ',
            'SECRET_KEY': 'ЕСТЬ' if os.environ.get('SECRET_KEY') else 'НЕТ',
            'total_users': User.query.count(),
            'total_games': Game.query.count(),
            'database_uri': app.config['SQLALCHEMY_DATABASE_URI'][:50] + '...' if app.config['SQLALCHEMY_DATABASE_URI'] else 'НЕТ'
        }
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/test_db')
def test_db():
    """Тест подключения к базе данных"""
    try:
        # Пробуем выполнить простой запрос
        user_count = User.query.count()
        return f"✅ База данных работает! Пользователей: {user_count}"
    except Exception as e:
        return f"❌ Ошибка базы данных: {str(e)}"

# ... остальные маршруты (logout, profile, edit_profile и т.д.) ...
# КОПИРУЕШЬ ИХ ИЗ ПРЕДЫДУЩЕГО КОДА

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('home'))

# --- Обработчики ошибок ---
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('403.html'), 403

@app.errorhandler(500)
def internal_error(error):
    print(f"❌ 500 ошибка: {error}")
    return render_template('500.html'), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 Запуск на порту: {port}")
    app.run(host='0.0.0.0', port=port, debug=DEBUG_MODE)