from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

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
    description = db.Column(db.String(500), default='Привет, я новый геймер!')
    contact = db.Column(db.String(100), default='Не указан')
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
    # ВНИМАНИЕ: Если вы удалили gamespecial.db, этот код создаст новую БД.
    db.create_all()


# --- 4. Маршруты (Логика сайта) ---

@app.route('/')
def home():
    users = User.query.all()
    return render_template('home.html', users=users)

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
            return redirect(url_for('add_game', username=user.username)) # Возвращаемся на страницу управления играми
            
    return render_template(
        'add_game.html', 
        user=user, 
        available_games=AVAILABLE_GAMES
    )

@app.route('/find_game', methods=['GET'])
def find_game():
    selected_game = request.args.get('game')
    found_users = []
    
    if selected_game:
        game_entries = Game.query.filter_by(game_title=selected_game).all()
        found_users = [entry.player for entry in game_entries]
        
    return render_template(
        'find_game.html', 
        available_games=AVAILABLE_GAMES,
        found_users=found_users,
        selected_game=selected_game
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
        user.description = request.form.get('description')
        user.contact = request.form.get('contact')
        db.session.commit()
        return redirect(url_for('view_profile', username=user.username))
        
    return render_template('edit_profile.html', user=user)

# НОВЫЙ МАРШРУТ: Удаление конкретной игры
@app.route('/delete_game/<username>/<int:game_id>', methods=['POST'])
def delete_game(username, game_id):
    # Находим игру по ID и проверяем, что она принадлежит пользователю
    game = Game.query.filter_by(id=game_id, player=User.query.filter_by(username=username).first()).first_or_404()
    
    db.session.delete(game)
    db.session.commit()
    
    return redirect(url_for('add_game', username=username))
    
if __name__ == '__main__':
    app.run(debug=True)