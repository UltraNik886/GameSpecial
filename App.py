from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy 
from sqlalchemy import distinct, func 
from werkzeug.security import generate_password_hash, check_password_hash
import os
import re
import secrets
from datetime import datetime

# --- Конфигурация ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production-12345'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gamespecial.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Доступные игры ---
AVAILABLE_GAMES = [
    "World of Warcraft", "Cyberpunk 2077", "Dota 2", "Counter-Strike 2", 
    "Baldur's Gate 3", "Minecraft", "Apex Legends", "Genshin Impact", "Rocket League"
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
    
    def __repr__(self):
        return f'<User {self.username}>'

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_title = db.Column(db.String(120), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    
    def __repr__(self):
        return f'<Game {self.game_title}>'

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=func.now())
    is_read = db.Column(db.Boolean, default=False)
    
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')
    
    def __repr__(self):
        return f'<Message {self.id} from {self.sender_id} to {self.receiver_id}>'

# --- Валидаторы ---
def validate_username(username):
    if len(username) < 3:
        return "Имя пользователя должно быть не менее 3 символов"
    if len(username) > 20:
        return "Имя пользователя должно быть не более 20 символов"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return "Имя пользователя может содержать только латинские буквы, цифры и _"
    return None

def validate_email(email):
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return "Некорректный формат email"
    return None

def validate_password(password):
    if len(password) < 6:
        return "Пароль должен быть не менее 6 символов"
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
            flash('У вас нет прав для выполнения этого действия', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# --- Создание базы данных ---
with app.app_context():
    db.create_all()

# --- Маршруты ---
@app.route('/')
def home():
    user_count = User.query.filter_by(is_active=True).count()
    game_count = db.session.query(func.count(distinct(Game.game_title))).scalar()
    
    users = User.query.filter_by(is_active=True).all()
    
    return render_template(
        'home.html', 
        users=users,
        user_count=user_count, 
        games_in_db=game_count
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        user = User.query.filter_by(username=username, is_active=True).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash(f'Добро пожаловать, {user.username}!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Неверное имя пользователя или пароль', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
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
            flash('Пользователь с таким именем уже существует', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Пользователь с таким email уже существует', 'error')
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            flash('Регистрация успешна! Теперь войдите в систему.', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('home'))

@app.route('/profile/<username>')
def view_profile(username):
    user = User.query.filter_by(username=username, is_active=True).first_or_404()
    return render_template('profile.html', user=user)

@app.route('/edit_profile/<username>', methods=['GET', 'POST'])
@login_required
@ownership_required
def edit_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    
    if request.method == 'POST':
        user.description = request.form.get('description', '')[:500]
        user.contact = request.form.get('contact', '')[:100]
        user.discord = request.form.get('discord', '')[:100]
        user.telegram = request.form.get('telegram', '')[:100]
        user.preferred_role = request.form.get('preferred_role', '')[:100]
        
        db.session.commit()
        flash('Профиль успешно обновлен!', 'success')
        return redirect(url_for('view_profile', username=user.username))
        
    return render_template('edit_profile.html', user=user)

@app.route('/add_game/<username>', methods=['GET', 'POST'])
@login_required
@ownership_required
def add_game(username):
    user = User.query.filter_by(username=username).first_or_404()
    
    if request.method == 'POST':
        game_title = request.form.get('game_title')
        if game_title and game_title in AVAILABLE_GAMES:
            exists = Game.query.filter_by(user_id=user.id, game_title=game_title).first()
            if not exists:
                new_game = Game(game_title=game_title, player=user)
                db.session.add(new_game)
                db.session.commit()
                flash(f'Игра {game_title} добавлена!', 'success')
            else:
                flash('Эта игра уже есть в вашем профиле', 'warning')
            return redirect(url_for('add_game', username=user.username))
            
    return render_template(
        'add_game.html', 
        user=user, 
        available_games=AVAILABLE_GAMES
    )

@app.route('/delete_game/<username>/<int:game_id>', methods=['POST'])
@login_required
@ownership_required
def delete_game(username, game_id):
    game = Game.query.filter_by(id=game_id).first_or_404()
    
    # Проверяем, что игра принадлежит пользователю
    if game.player.username != username:
        flash('Ошибка доступа', 'error')
        return redirect(url_for('home'))
    
    db.session.delete(game)
    db.session.commit()
    flash('Игра удалена из профиля', 'success')
    
    return redirect(url_for('add_game', username=username))

@app.route('/find_game', methods=['GET'])
def find_game():
    selected_games = request.args.getlist('games') 
    contact_filters = request.args.getlist('contact_filter') 
    
    # Базовый запрос
    query = User.query.filter_by(is_active=True)
    
    # Фильтрация по играм
    if selected_games:
        # Для каждой выбранной игры проверяем наличие у пользователя
        for game_title in selected_games:
            query = query.filter(User.games.any(game_title=game_title))
    
    found_users = query.all()
    
    # Дополнительная фильтрация по контактам
    if contact_filters:
        filtered_users = []
        for user in found_users:
            has_required_contact = False
            if 'discord' in contact_filters and user.discord:
                has_required_contact = True
            if 'telegram' in contact_filters and user.telegram:
                has_required_contact = True
            if has_required_contact:
                filtered_users.append(user)
        found_users = filtered_users
                
    return render_template(
        'find_game.html', 
        available_games=AVAILABLE_GAMES,
        found_users=found_users,
        selected_games=selected_games,
        contact_filters=contact_filters 
    )

@app.route('/delete_user/<username>', methods=['POST'])
@login_required
@ownership_required
def delete_user(username):
    user = User.query.filter_by(username=username).first_or_404()
    
    # Мягкое удаление
    user.is_active = False
    db.session.commit()
    
    session.clear()
    flash('Ваш профиль был удален', 'info')
    return redirect(url_for('home'))

# --- Маршруты чата ---
@app.route('/messages')
@login_required
def messages():
    """Страница со списком чатов"""
    user_id = session['user_id']
    
    # Получаем последние сообщения с каждым пользователем
    recent_messages = db.session.query(
        Message,
        func.max(Message.timestamp).label('max_timestamp')
    ).filter(
        (Message.sender_id == user_id) | (Message.receiver_id == user_id)
    ).group_by(
        db.case(
            (Message.sender_id == user_id, Message.receiver_id),
            else_=Message.sender_id
        )
    ).order_by(db.desc('max_timestamp')).all()
    
    chats = []
    for msg, timestamp in recent_messages:
        other_user = msg.receiver if msg.sender_id == user_id else msg.sender
        unread_count = Message.query.filter_by(
            sender_id=other_user.id,
            receiver_id=user_id,
            is_read=False
        ).count()
        
        chats.append({
            'user': other_user,
            'last_message': msg,
            'unread_count': unread_count,
            'timestamp': timestamp
        })
    
    return render_template('messages.html', chats=chats)

@app.route('/chat/<username>')
@login_required
def chat(username):
    """Страница чата с конкретным пользователем"""
    other_user = User.query.filter_by(username=username, is_active=True).first_or_404()
    current_user_id = session['user_id']
    
    if other_user.id == current_user_id:
        flash('Нельзя писать самому себе', 'error')
        return redirect(url_for('messages'))
    
    # Помечаем сообщения как прочитанные
    Message.query.filter_by(
        sender_id=other_user.id,
        receiver_id=current_user_id,
        is_read=False
    ).update({'is_read': True})
    db.session.commit()
    
    # Получаем историю сообщений
    messages_history = Message.query.filter(
        ((Message.sender_id == current_user_id) & (Message.receiver_id == other_user.id)) |
        ((Message.sender_id == other_user.id) & (Message.receiver_id == current_user_id))
    ).order_by(Message.timestamp.asc()).all()
    
    return render_template('chat.html', 
                         other_user=other_user, 
                         messages=messages_history)

@app.route('/send_message/<username>', methods=['POST'])
@login_required
def send_message(username):
    """Отправка сообщения"""
    other_user = User.query.filter_by(username=username, is_active=True).first_or_404()
    current_user_id = session['user_id']
    
    if other_user.id == current_user_id:
        flash('Нельзя писать самому себе', 'error')
        return redirect(url_for('messages'))
    
    content = request.form.get('content', '').strip()
    
    if not content:
        flash('Сообщение не может быть пустым', 'error')
    elif len(content) > 1000:
        flash('Сообщение слишком длинное', 'error')
    else:
        message = Message(
            sender_id=current_user_id,
            receiver_id=other_user.id,
            content=content
        )
        db.session.add(message)
        db.session.commit()
        flash('Сообщение отправлено!', 'success')
    
    return redirect(url_for('chat', username=username))

@app.route('/api/unread_count')
@login_required
def unread_count():
    """API для получения количества непрочитанных сообщений"""
    count = Message.query.filter_by(
        receiver_id=session['user_id'],
        is_read=False
    ).count()
    return jsonify({'unread_count': count})

# --- Обработчики ошибок ---
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('403.html'), 403

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)