import setup_dependencies

import logging
from flask import Flask, request, jsonify, render_template, g, abort
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from functools import wraps
import sqlite3
import base64
from datetime import datetime
from typing import Callable, Optional, Any, List, Dict, Union

# Логирование
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Создание приложения Flask и инициализация SocketIO
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = 'secret!'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

DATABASE = 'board.db'

# Инициализация базы данных
class Database:
    @staticmethod
    def init_db() -> None:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL UNIQUE,
                    user_code TEXT NOT NULL,
                    last_active TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    board TEXT NOT NULL,
                    title TEXT NOT NULL,
                    image TEXT,
                    date TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    last_message TEXT,
                    popularity_score REAL DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    date TEXT NOT NULL,
                    image TEXT,
                    bump INTEGER DEFAULT 0,
                    FOREIGN KEY (thread_id) REFERENCES threads (id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS thread_views (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    view_count INTEGER DEFAULT 0,
                    FOREIGN KEY (thread_id) REFERENCES threads (id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            conn.commit()


# Вспомогательные функции
class Utils:
    @staticmethod
    def to_base36(num: int) -> str:
        chars = "0123456789abcdefghijklmnopqrstuvwxyz"
        base36 = ""
        while num > 0:
            num, i = divmod(num, 36)
            base36 = chars[i] + base36
        return base36.zfill(8)

# Декоратор для обновления времени последней активности
def update_last_active(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        if 'user_id' in g:
            try:
                with sqlite3.connect(DATABASE) as conn:
                    cursor = conn.cursor()
                    cursor.execute('UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE id = ?', (g.user_id,))
                    conn.commit()
                    logger.info(f"Updated last active for user_id {g.user_id}")
            except Exception as e:
                logger.error(f"Error updating last active timestamp: {e}")
        return f(*args, **kwargs)
    return decorated_function

# Загрузка пользователя перед запросом
@app.before_request
def load_user() -> None:
    ip_address: str = request.remote_addr
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE ip_address = ?', (ip_address,))
        user = cursor.fetchone()
        g.user_id = user[0] if user else None
        logger.info(f"Loaded user_id {g.user_id} for IP {ip_address}")

# Маршруты и обработчики API
@app.route('/api/login', methods=['POST'])
def login() -> Any:
    try:
        ip_address: str = request.remote_addr
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, user_code FROM users WHERE ip_address = ?', (ip_address,))
            user = cursor.fetchone()
            if not user:
                cursor.execute('SELECT COUNT(*) FROM users')
                user_count: int = cursor.fetchone()[0]
                user_code: str = Utils.to_base36(user_count + 1)
                cursor.execute('INSERT INTO users (ip_address, user_code) VALUES (?, ?)', (ip_address, user_code))
                conn.commit()
                user_id: int = cursor.lastrowid
                logger.info(f"Created new user with id {user_id} and code {user_code}")
            else:
                user_id, user_code = user[0], user[1]
                logger.info(f"Existing user login with id {user_id} and code {user_code}")
        return jsonify({'user_id': user_id, 'user_code': user_code})
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/<int:user_id>', methods=['GET'])
def get_user(user_id: int) -> Any:
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_code FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
            if user:
                logger.info(f"Fetched user with id {user_id}")
                return jsonify({'user_code': user[0]})
            else:
                logger.warning(f"User not found with id {user_id}")
                return jsonify({'error': 'User not found'}), 404
    except Exception as e:
        logger.error(f"Error fetching user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/threads', methods=['POST'])
@update_last_active
def create_thread() -> Any:
    try:
        data: Dict[str, Any] = request.json
        board: str = data['board']
        title: str = data['title']
        image: Optional[str] = data.get('image')
        user_id: int = data['user_id']
        date: str = datetime.now().strftime('%d %B %Y %H:%M')

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO threads (board, title, image, date, user_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (board, title, image, date, user_id))
            conn.commit()
            thread_id: int = cursor.lastrowid
            logger.info(f"Created new thread with id {thread_id} on board {board}")

        socketio.emit('new_thread', {'id': thread_id, 'board': board, 'title': title, 'image': image, 'date': date, 'user_id': user_id}, room=board)

        return jsonify({'id': thread_id, 'board': board, 'title': title, 'image': image, 'date': date, 'user_id': user_id})
    except Exception as e:
        logger.error(f"Error creating thread: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/threads/<board>', methods=['GET'])
def get_threads(board: str) -> Any:
    try:
        if not board.isalnum():
            logger.warning(f"Invalid board name: {board}")
            return jsonify({'error': 'Invalid board name'}), 400
        
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM threads WHERE board = ?', (board,))
            threads = cursor.fetchall()

        result: List[Dict[str, Union[int, str, Optional[str]]]] = []
        for thread in threads:
            result.append({
                'id': thread[0],
                'board': thread[1],
                'title': thread[2],
                'image': thread[3],
                'date': thread[4],
                'user_id': thread[5],
                'last_message': thread[6]
            })

        logger.info(f"Fetched threads for board {board}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching threads: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/threads/<int:thread_id>/messages', methods=['GET'])
def get_messages(thread_id: int) -> Any:
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT m.id, m.message, m.date, u.user_code, m.image
                FROM messages m
                JOIN users u ON m.user_id = u.id
                WHERE m.thread_id = ?
            ''', (thread_id,))
            messages = cursor.fetchall()

        result: List[Dict[str, Union[int, str, Optional[str]]]] = []
        for message in messages:
            result.append({
                'id': message[0],
                'message': message[1],
                'date': message[2],
                'user_code': message[3],
                'image': message[4]
            })

        logger.info(f"Fetched messages for thread {thread_id}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching messages: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/threads/<int:thread_id>/messages/delete_old', methods=['DELETE'])
def delete_old_messages(thread_id: int) -> Any:
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM messages
                WHERE id IN (
                    SELECT id FROM messages
                    WHERE thread_id = ?
                    ORDER BY date ASC
                    LIMIT 20
                )
            ''', (thread_id,))
            conn.commit()

        logger.info(f"Deleted old messages for thread {thread_id}")
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Error deleting old messages: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/threads/<board>/<int:thread_id>/update_date', methods=['PUT'])
@update_last_active
def update_thread_date(board: str, thread_id: int) -> Any:
    try:
        new_date: str = datetime.now().strftime('%d %B %Y %H:%M')
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE threads
                SET date = ?
                WHERE id = ? AND board = ?
            ''', (new_date, thread_id, board))
            conn.commit()

        return jsonify({'status': 'success', 'new_date': new_date})
    except Exception as e:
        logger.error(f"Error updating thread date: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/messages', methods=['POST'])
@update_last_active
def create_message() -> Any:
    try:
        thread_id: int = int(request.form['thread_id'])
        user_id: int = int(request.form['user_id'])
        message: str = request.form['message']
        date: str = datetime.now().strftime('%d %B %Y %H:%M')

        logger.debug(f"Received message data: thread_id={thread_id}, user_id={user_id}, message={message}")
        update_popularity(thread_id)

        image: Optional[str] = None
        if 'image' in request.files:
            image_file = request.files['image']
            image_data: bytes = image_file.read()
            image = base64.b64encode(image_data).decode('utf-8')
            logger.debug(f"Image uploaded: {image_file.filename}")

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages (thread_id, user_id, message, date, image)
                VALUES (?, ?, ?, ?, ?)
            ''', (thread_id, user_id, message, date, image))
            conn.commit()
            message_id: int = cursor.lastrowid

            cursor.execute('''
                UPDATE threads SET last_message = ? WHERE id = ?
            ''', (message, thread_id))
            conn.commit()

        logger.info(f"Created new message with id {message_id} in thread {thread_id}")

        socketio.emit('new_message', {
            'id': message_id, 
            'thread_id': thread_id, 
            'user_id': user_id, 
            'message': message, 
            'date': date, 
            'image': image
        }, room=str(thread_id))

        return jsonify({'id': message_id, 'thread_id': thread_id, 'user_id': user_id, 'message': message, 'date': date, 'image': image})
    except Exception as e:
        logger.error(f"Error creating message: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/threads/<int:thread_id>/last_message', methods=['GET'])
def get_last_message(thread_id: int) -> Any:
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT m.id, m.message, m.date, u.user_code, m.image
                FROM messages m
                JOIN users u ON m.user_id = u.id
                WHERE m.thread_id = ?
                ORDER BY m.date DESC
                LIMIT 1
            ''', (thread_id,))
            message = cursor.fetchone()

        if message:
            result = {
                'id': message[0],
                'message': message[1],
                'date': message[2],
                'user_code': message[3],
                'image': message[4]
            }
            return jsonify(result)
        else:
            return jsonify({'error': 'No messages found'}), 404
    except Exception as e:
        logger.error(f"Error fetching last message: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats() -> Any:
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM threads')
            post_count: int = cursor.fetchone()[0]

            cursor.execute('''
                SELECT COUNT(*) FROM users 
                WHERE last_active > datetime('now', '-5 minutes')
            ''')
            online_count: int = cursor.fetchone()[0]

            cursor.execute('SELECT SUM(LENGTH(image)) FROM messages WHERE image IS NOT NULL')
            image_weight: int = cursor.fetchone()[0] or 0

            cursor.execute('SELECT SUM(LENGTH(message)) FROM messages')
            message_text_weight: int = cursor.fetchone()[0] or 0

            cursor.execute('SELECT SUM(LENGTH(title)) FROM threads')
            title_text_weight: int = cursor.fetchone()[0] or 0

            total_weight: int = image_weight + message_text_weight + title_text_weight
            total_weight_mb: float = total_weight / (1024 * 1024)

        logger.info("Fetched stats")
        return jsonify({
            'post_count': post_count,
            'online_count': online_count,
            'archive_weight': total_weight_mb
        })
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return jsonify({'error': str(e)}), 500

def update_popularity(thread_id: int) -> None:
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT COUNT(*) FROM messages WHERE thread_id = ?
            ''', (thread_id,))
            message_count = cursor.fetchone()[0]

            cursor.execute('''
                SELECT view_count FROM thread_views WHERE thread_id = ?
            ''', (thread_id,))
            view_count = cursor.fetchone()[0]

            cursor.execute('''
                SELECT COUNT(*) FROM messages WHERE thread_id = ? AND bump = 1
            ''', (thread_id,))
            bump_count = cursor.fetchone()[0]

            cursor.execute('''
                SELECT date, last_message FROM threads WHERE id = ?
            ''', (thread_id,))
            thread_info = cursor.fetchone()
            thread_date = datetime.datetime.strptime(thread_info[0], '%Y-%m-%d %H:%M:%S')
            last_message_date = datetime.datetime.strptime(thread_info[1], '%Y-%m-%d %H:%M:%S')

            age_in_hours = (datetime.datetime.now() - thread_date).total_seconds() / 3600
            last_active_in_hours = (datetime.datetime.now() - last_message_date).total_seconds() / 3600

            age_factor = 1 / (1 + age_in_hours / 24)
            last_active_factor = 1 / (1 + last_active_in_hours / 24)

            popularity_score = (
                (message_count * 0.25) + 
                (view_count * 0.25) + 
                (bump_count * 0.25) + 
                (age_factor * 0.125) + 
                (last_active_factor * 0.125)
            )

            cursor.execute('''
                UPDATE threads SET popularity_score = ? WHERE id = ?
            ''', (popularity_score, thread_id))
            conn.commit()
            logger.info(f"Updated popularity score for thread_id {thread_id}")

            cursor.execute('''
                SELECT id, board, title, image, date, last_message, popularity_score
                FROM threads
                ORDER BY popularity_score DESC
                LIMIT 4
            ''')
            popular_threads = cursor.fetchall()
            socketio.emit('popular_threads_update', popular_threads)

    except Exception as e:
        logger.error(f"Error updating popularity score: {e}")


@app.route('/api/popular_threads', methods=['GET'])
def get_popular_threads() -> Any:
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, board, title, image, date, last_message, popularity_score
                FROM threads
                ORDER BY popularity_score DESC
                LIMIT 4
            ''')
            threads = cursor.fetchall()
            logger.info(f"Fetched popular threads")
        return jsonify(threads)
    except Exception as e:
        logger.error(f"Error fetching popular threads: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/personalized_threads', methods=['GET'])
@update_last_active
def get_personalized_threads() -> Any:
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'User ID is required'}), 400

    try:
        user_id = int(user_id)
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            # Здесь можно добавить логику для персонализированного получения тем для пользователя
            cursor.execute('SELECT * FROM threads WHERE user_id = ? LIMIT 4', (user_id,))
            threads = cursor.fetchall()

        result: List[Dict[str, Union[int, str, Optional[str]]]] = []
        for thread in threads:
            result.append({
                'id': thread[0],
                'board': thread[1],
                'title': thread[2],
                'image': thread[3],
                'date': thread[4],
                'user_id': thread[5],
                'last_message': thread[6],
                'popularity_score': thread[7]
            })
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching personalized threads: {e}")
        return jsonify({'error': str(e)}), 500

def increment_view_count(thread_id: int, user_id: int) -> None:
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT view_count FROM thread_views WHERE thread_id = ? AND user_id = ?', (thread_id, user_id))
            view = cursor.fetchone()
            if view:
                cursor.execute('UPDATE thread_views SET view_count = view_count + 1 WHERE thread_id = ? AND user_id = ?', (thread_id, user_id))
            else:
                cursor.execute('INSERT INTO thread_views (thread_id, user_id, view_count) VALUES (?, ?, 1)', (thread_id, user_id))
            conn.commit()
            logger.info(f"Incremented view count for thread_id {thread_id} by user_id {user_id}")
    except Exception as e:
        logger.error(f"Error incrementing view count: {e}")


# Маршруты для рендеринга HTML страниц
@app.route('/')
def index() -> str:
    return render_template('index.html')

@app.route('/board.html')
def board_page() -> str:
    board_name: Optional[str] = request.args.get('board')
    if board_name and not board_name.isalnum():
        logger.warning(f"Invalid board name parameter: {board_name}")
        abort(400, description="Invalid board name")
    return render_template('board.html', board=board_name)

@app.route('/thread.html')
def thread_page() -> str:
    board_name: Optional[str] = request.args.get('board')
    thread_id: Optional[str] = request.args.get('threadId')

    update_popularity(thread_id)
    if board_name and not board_name.isalnum():
        logger.warning(f"Invalid board name parameter: {board_name}")
        abort(400, description="Invalid board name")
    if thread_id and not thread_id.isdigit():
        logger.warning(f"Invalid threadId parameter: {thread_id}")
        abort(400, description="Invalid threadId")
    
    if thread_id:
        increment_view_count(int(thread_id))
    
    return render_template('thread.html', board=board_name, thread_id=thread_id)

# События сокетов
@socketio.on('join')
def on_join(data: Dict[str, Any]) -> None:
    board: str = data['board']
    thread_id: Optional[str] = data.get('thread_id')
    room: str = board if not thread_id else f"{board}_{thread_id}"
    join_room(room)
    logger.info(f"User joined room: {room}")

@socketio.on('leave')
def on_leave(data: Dict[str, Any]) -> None:
    board: str = data['board']
    thread_id: Optional[str] = data.get('thread_id')
    room: str = board if not thread_id else f"{board}_{thread_id}"
    leave_room(room)
    logger.info(f"User left room: {room}")

@socketio.on('new_thread')
def on_new_thread(data: Dict[str, Any]) -> None:
    emit('new_thread', data, broadcast=True)

@socketio.on('new_message')
def handle_new_message(data):
    try:
        user_id = data['user_id']
        thread_id = data['thread_id']
        message = data['message']
        image = data.get('image')
        bump = data.get('bump', 0)
        date = datetime.now().strftime('%d %B %Y %H:%M')

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages (thread_id, user_id, message, date, image, bump)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (thread_id, user_id, message, date, image, bump))
            conn.commit()
            message_id = cursor.lastrowid

            # Emit new message to the thread room
            emit('new_message', {'id': message_id, 'thread_id': thread_id, 'user_id': user_id, 'message': message, 'date': date, 'image': image}, room=thread_id)

            # Fetch personalized threads for the user
            cursor.execute('''
                SELECT t.id, t.board, t.title, t.image, t.date, t.user_id, t.last_message
                FROM threads t
                JOIN messages m ON t.id = m.thread_id
                WHERE m.user_id = ?
                GROUP BY t.id
                ORDER BY MAX(m.date) DESC
            ''', (user_id,))
            personalized_threads = cursor.fetchall()

            result = []
            for thread in personalized_threads:
                result.append({
                    'id': thread[0],
                    'board': thread[1],
                    'title': thread[2],
                    'image': thread[3],
                    'date': thread[4],
                    'user_id': thread[5],
                    'last_message': thread[6]
                })

            # Emit personalized threads to the user
            emit('personalized_threads', result, room=user_id)

            logger.info(f"Added new message with id {message_id} to thread {thread_id}")
    except Exception as e:
        logger.error(f"Error handling new message: {e}")

# Запуск приложения
if __name__ == '__main__':
    Database.init_db()
    socketio.run(app, debug=True)
