from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy 
from sqlalchemy import distinct, func 

# --- 0. Доступные игры ---
AVAILABLE_GAMES = [
    "World of Warcraft", 
    "Cyberpunk 2077", 
    "Dota 2", 
    "Counter-Strike 2", 
    "Baldur's Gate 3",
    "Minecraft",
    "Apex Legends",
    "Genshin Impact",
    "Rocket League"
]

# --- 1. Настройка приложения и базы данных ---
app = Flask(__name__)

# Используем базу данных SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gamespecial.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- 2. Модели базы данных (Таблицы) ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(500), default='') 
    contact = db.Column(db.String(100), default='')
    
    discord = db.Column(db.String(100), default='')
    telegram = db.Column(db.String(100), default='')
    preferred_role = db.Column(db.String(100), default='') 
    
    # games остается lazy='dynamic'
    games = db.relationship('Game', backref='player', lazy='dynamic')
    
    def __repr__(self):
        return f'<User {self.username}>'

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_title = db.Column(db.String(120), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    def __repr__(self):
        return f'<Game {self.game_title}>'

# --- 3. Создание базы данных (Запуск) ---

with app.app_context():
    db.create_all()


# --- 4. Маршруты (Логика сайта) ---

@app.route('/')
def home():
    user_count = db.session.query(User).count()
    game_count_query = db.session.query(func.count(distinct(Game.game_title)))
    games_in_db = game_count_query.scalar()
    
    # Получаем список пользователей (нужен для корректной работы шаблона)
    users = User.query.all()
    
    # Передаем список users в шаблон
    return render_template(
        'home.html', 
        users=users,
        user_count=user_count, 
        games_in_db=games_in_db 
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        new_username = request.form.get('username')
        if new_username:
            user = User(username=new_username) 
            db.session.add(user)
            db.session.commit()
            return redirect(url_for('view_profile', username=new_username)) 
            
    return render_template('register.html')

@app.route('/add_game/<username>', methods=['GET', 'POST']) 
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
            return redirect(url_for('add_game', username=user.username)) 
            
    return render_template(
        'add_game.html', 
        user=user, 
        available_games=AVAILABLE_GAMES
    )

# ЛОГИКА ПОИСКА (Мультифильтрация игр и контактов)
@app.route('/find_game', methods=['GET'])
def find_game():
    selected_games = request.args.getlist('games') 
    contact_filters = request.args.getlist('contact_filter') 
    
    all_users = User.query.all()
    found_users = []
    
    for user in all_users:
        
        # --- ФИЛЬТР ИГР ---
        passes_game_filter = True
        if selected_games:
            # Используем .all() для получения списка игр, чтобы избежать ошибки AppenderQuery
            user_game_titles = [game.game_title for game in user.games.all()] 
            if not all(game_title in user_game_titles for game_title in selected_games):
                passes_game_filter = False
        
        # --- ФИЛЬТР КОНТАКТОВ ---
        passes_contact_filter = True
        if contact_filters:
            has_required_contact = False
            
            if 'discord' in contact_filters and user.discord:
                has_required_contact = True
            if 'telegram' in contact_filters and user.telegram:
                has_required_contact = True
            
            if not has_required_contact:
                passes_contact_filter = False
                
        # --- КОНЕЧНОЕ РЕШЕНИЕ ---
        if passes_game_filter and passes_contact_filter:
            found_users.append(user)
                
    return render_template(
        'find_game.html', 
        available_games=AVAILABLE_GAMES,
        found_users=found_users,
        selected_games=selected_games,
        contact_filters=contact_filters 
    )

@app.route('/delete_user/<username>', methods=['POST']) 
def delete_user(username):
    user = User.query.filter_by(username=username).first_or_404()
    Game.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('home'))

@app.route('/profile/<username>')
def view_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    return render_template('profile.html', user=user)

@app.route('/edit_profile/<username>', methods=['GET', 'POST'])
def edit_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    
    if request.method == 'POST':
        user.description = request.form.get('description') or ''
        user.contact = request.form.get('contact') or ''
        
        user.discord = request.form.get('discord') or ''
        user.telegram = request.form.get('telegram') or ''
        user.preferred_role = request.form.get('preferred_role') or ''
        
        db.session.commit()
        return redirect(url_for('view_profile', username=user.username))
        
    return render_template('edit_profile.html', user=user)

@app.route('/delete_game/<username>/<int:game_id>', methods=['POST'])
def delete_game(username, game_id):
    game = Game.query.filter_by(id=game_id, player=User.query.filter_by(username=username).first()).first_or_404()
    
    db.session.delete(game)
    db.session.commit()
    
    return redirect(url_for('add_game', username=username))
    
if __name__ == '__main__':
    app.run(debug=True)