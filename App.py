from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy 
from sqlalchemy import distinct, func, text
from werkzeug.security import generate_password_hash, check_password_hash
import os
import re

# --- Конфигурация ---
app = Flask(__name__)

# Базовая конфигурация
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Настройка базы данных
database_url = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url

db = SQLAlchemy(app)

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

# --- ДОСТУПНЫЕ ИГРЫ ---
AVAILABLE_GAMES = [
    "World of Warcraft", "Cyberpunk 2077", "Dota 2", "Counter-Strike 2", 
    "Baldur's Gate 3", "Minecraft", "Apex Legends", "Genshin Impact", "Rocket League"
]

# Создаем таблицы
with app.app_context():
    db.create_all()
    print("✅ База данных готова")

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

# --- АДМИН СИСТЕМА ---
ADMIN_USERNAMES = ['MollNik']

def is_admin():
    return session.get('username') in ADMIN_USERNAMES

# --- ОСНОВНЫЕ МАРШРУТЫ ---
@app.route('/')
def home():
    try:
        user_count = User.query.filter_by(is_active=True).count()
        users = User.query.filter_by(is_active=True).order_by(User.created_at.desc()).limit(20).all()
        
        return render_template('home.html', 
                             users=users, 
                             user_count=user_count,
                             available_games=AVAILABLE_GAMES)
    except Exception as e:
        return render_template('home.html', 
                             users=[], 
                             user_count=0,
                             available_games=AVAILABLE_GAMES)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            
            if not username or not password:
                flash('Заполните все поля', 'error')
                return render_template('login.html')
            
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
            flash('Произошла ошибка при входе. Попробуйте еще раз.', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            # Валидация
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
                
                if username in ADMIN_USERNAMES:
                    flash('👑 Вы зарегистрировались как администратор!', 'success')
                
                return redirect(url_for('login'))
                
        except Exception as e:
            flash('Произошла ошибка при регистрации. Попробуйте еще раз.', 'error')
    
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
    except:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('home'))

@app.route('/my_profile')
@login_required
def my_profile():
    """Профиль текущего пользователя"""
    try:
        user = User.query.get(session['user_id'])
        return render_template('profile.html', user=user)
    except Exception as e:
        flash('Ошибка при загрузке профиля', 'error')
        return redirect(url_for('home'))

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Редактирование профиля"""
    try:
        user = User.query.get(session['user_id'])
        
        if request.method == 'POST':
            user.description = request.form.get('description', '')
            user.contact = request.form.get('contact', '')
            user.discord = request.form.get('discord', '')
            user.telegram = request.form.get('telegram', '')
            user.preferred_role = request.form.get('preferred_role', '')
            
            # Обновляем игры
            user.games.delete()
            selected_games = request.form.getlist('games')
            for game_title in selected_games:
                if game_title in AVAILABLE_GAMES:
                    game = Game(game_title=game_title, user_id=user.id)
                    db.session.add(game)
            
            db.session.commit()
            flash('Профиль обновлен!', 'success')
            return redirect(url_for('my_profile'))
        
        # GET запрос - показываем форму
        user_games = [game.game_title for game in user.games]
        return render_template('edit_profile.html', 
                             user=user, 
                             available_games=AVAILABLE_GAMES,
                             user_games=user_games)
        
    except Exception as e:
        flash('Ошибка при обновлении профиля', 'error')
        return redirect(url_for('my_profile'))

@app.route('/find_game')
def find_game():
    try:
        selected_games = request.args.getlist('games') 
        users = User.query.filter_by(is_active=True).all()
        
        if selected_games:
            filtered_users = []
            for user in users:
                user_games = [game.game_title for game in user.games]
                if any(game in user_games for game in selected_games):
                    filtered_users.append(user)
            users = filtered_users
                
        return render_template('find_game.html', 
                             available_games=AVAILABLE_GAMES,
                             found_users=users,
                             selected_games=selected_games)
    except:
        return render_template('find_game.html', 
                             available_games=AVAILABLE_GAMES,
                             found_users=[],
                             selected_games=[])

# --- АДМИН ПАНЕЛЬ ---
@app.route('/admin')
@login_required
def admin_panel():
    """Админ панель"""
    try:
        if not is_admin():
            flash('❌ Доступ запрещен!', 'error')
            return redirect(url_for('home'))
        
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        total_games = Game.query.count()
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        
        return render_template('admin_panel.html',
                         total_users=total_users,
                         active_users=active_users, 
                         total_games=total_games,
                         recent_users=recent_users)
    except Exception as e:
        flash(f'Ошибка админки: {str(e)}', 'error')
        return redirect(url_for('home'))

# --- СООБЩЕНИЯ ---
@app.route('/messages')
@login_required
def messages():
    """Страница сообщений"""
    return render_template('messages.html')

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    """Отправка сообщения"""
    flash('Функция сообщений скоро будет доступна!', 'info')
    return redirect(url_for('home'))

# --- ДИАГНОСТИКА ---
@app.route('/debug')
def debug():
    try:
        info = {
            'RAILWAY_ENVIRONMENT': os.environ.get('RAILWAY_ENVIRONMENT'),
            'DATABASE_URL': 'ЕСТЬ' if os.environ.get('DATABASE_URL') else 'НЕТ',
            'SECRET_KEY': 'ЕСТЬ' if os.environ.get('SECRET_KEY') else 'НЕТ',
            'total_users': User.query.count(),
            'total_games': Game.query.count()
        }
    except:
        info = {
            'RAILWAY_ENVIRONMENT': os.environ.get('RAILWAY_ENVIRONMENT'),
            'DATABASE_URL': 'ЕСТЬ' if os.environ.get('DATABASE_URL') else 'НЕТ',
            'SECRET_KEY': 'ЕСТЬ' if os.environ.get('SECRET_KEY') else 'НЕТ',
            'error': 'Ошибка базы данных'
        }
    return jsonify(info)

@app.route('/test_db')
def test_db():
    try:
        db.session.execute(text('SELECT 1'))
        user_count = User.query.count()
        return jsonify({
            'status': 'success',
            'message': 'База данных подключена',
            'user_count': user_count
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Ошибка БД: {str(e)}'
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)