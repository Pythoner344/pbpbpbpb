import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import config

def get_db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                image_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)
        conn.commit()

def register_user(username, password):
    try:
        with get_db() as conn:
            hash_pwd = generate_password_hash(password)
            conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hash_pwd))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False

def check_user(username, password):
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            return dict(user)
    return None

# НОВЫЙ МЕТОД: Получить юзера по ID
def get_user_by_id(user_id):
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(user) if user else None

# НОВЫЙ МЕТОД: Обновить пароль
def update_password(user_id, new_password):
    with get_db() as conn:
        hash_pwd = generate_password_hash(new_password)
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_pwd, user_id))
        conn.commit()
        return True

def create_chat(user_id, title="Новый чат"):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chats (user_id, title) VALUES (?, ?)", (user_id, title))
        conn.commit()
        return cursor.lastrowid

def get_user_chats(user_id):
    with get_db() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM chats WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()]

def get_chat_messages(chat_id):
    with get_db() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC", (chat_id,)).fetchall()]

def save_message(chat_id, role, content, image_path=None):
    with get_db() as conn:
        conn.execute("INSERT INTO messages (chat_id, role, content, image_path) VALUES (?, ?, ?, ?)", 
                     (chat_id, role, content, image_path))
        conn.commit()

def update_chat_title(chat_id, title):
    with get_db() as conn:
        conn.execute("UPDATE chats SET title = ? WHERE id = ?", (title[:30], chat_id))
        conn.commit()