import os
import glob
import sqlite3
import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, abort
from google import genai
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# -----------------------------
# 1. ЗАГРУЗКА КЛЮЧА
# -----------------------------
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

client = None
if API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
        client.models.generate_content(model="gemini-2.0-flash", contents="Проверка")
        print("✅ Ключ Gemini API корректен")
    except Exception as e:
        print("⚠️ Ошибка Gemini:", e)
else:
    print("⚠️ Ключ Gemini отсутствует, Gemini API отключен.")

# -----------------------------
# 2. FLASK
# -----------------------------
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = "uploads"
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
CHAT_DIR = "chats"
os.makedirs(CHAT_DIR, exist_ok=True)
DB_PATH = "chat_history.db"
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# -----------------------------
# 3. БАЗА ДАННЫХ
# -----------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            title TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_name TEXT,
            sender TEXT,
            text TEXT,
            image_url TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def add_chat(chat_name, title=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO chats (name, title) VALUES (?, ?)", (chat_name, title))
    conn.commit()
    conn.close()

def update_chat_title(chat_name, title):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE chats SET title=? WHERE name=?", (title, chat_name))
    conn.commit()
    conn.close()

def add_message(chat_name, sender, text, image_url=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (chat_name, sender, text, image_url) VALUES (?, ?, ?, ?)",
        (chat_name, sender, text, image_url)
    )
    conn.commit()
    conn.close()

def get_all_chats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, COALESCE(title, name) FROM chats ORDER BY id DESC")
    rows = [{"name": r[0], "title": r[1]} for r in c.fetchall()]
    conn.close()
    return rows

def get_messages(chat_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT sender, text, image_url FROM messages WHERE chat_name=? ORDER BY id", (chat_name,))
    msgs = [{"sender": r[0], "text": r[1], "image_url": r[2]} for r in c.fetchall()]
    conn.close()
    return msgs

# -----------------------------
# 4. Утилиты для файлов
# -----------------------------
def next_chat_file():
    files = sorted(glob.glob(os.path.join(CHAT_DIR, "chat_*.txt")))
    next_id = max([int(f.split('_')[1].split('.')[0]) for f in files], default=0) + 1
    new_file = f"chat_{next_id}.txt"
    open(os.path.join(CHAT_DIR, new_file), "w", encoding="utf-8").close()
    add_chat(new_file)
    return new_file

# -----------------------------
# 5. Gemini
# -----------------------------
def ask_gemini(user_text, image_path=None):
    if not client:
        return f"(offline) {user_text}"
    try:
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                img = f.read()
            resp = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[{"role":"user","parts":[
                    {"text": user_text or ""},
                    {"inline_data":{"mime_type":"image/jpeg","data": img}}
                ]}]
            )
        else:
            resp = client.models.generate_content(model="gemini-2.0-flash", contents=user_text)
        return resp.text
    except Exception as e:
        return f"Ошибка Gemini: {e}"

# -----------------------------
# 6. ROUTES
# -----------------------------
@app.route("/")
def index():
    chats = get_all_chats()
    current = chats[0]["name"] if chats else next_chat_file()
    messages = get_messages(current)
    return render_template("index.html", history=messages, chats=chats, current=current)

@app.route("/get", methods=["POST"])
def get_response():
    data = request.json or {}
    chat_name = data.get("chat")
    msg = data.get("msg", "")
    image_url = data.get("image_url")

    if not chat_name:
        chat_name = next_chat_file()

    # путь к файлу для Gemini
    image_path = None
    if image_url and image_url.startswith("/uploads/"):
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], os.path.basename(image_url))

    response = ask_gemini(msg, image_path)
    add_message(chat_name, "user", msg, image_url)
    add_message(chat_name, "bot", response)

    # если это первый вопрос — сделать его заголовком чата
    messages = get_messages(chat_name)
    if len(messages) == 2:  # первый обмен user + bot
        short_title = msg[:40] + ("…" if len(msg) > 40 else "")
        update_chat_title(chat_name, short_title)

    return jsonify({"response": response, "chat_name": chat_name})

@app.route("/upload_image", methods=["POST"])
def upload_image():
    if 'image' not in request.files:
        return jsonify({"error": "Нет файла"}), 400
    file = request.files['image']
    if not file.filename:
        return jsonify({"error": "Пустое имя файла"}), 400
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Недопустимый формат"}), 400
    filename = secure_filename(file.filename)
    filename = f"{datetime.datetime.now().timestamp()}_{filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    return jsonify({"image_url": f"/uploads/{filename}"})

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/get_chats")
def get_chats():
    return jsonify(get_all_chats())

@app.route("/load_chat", methods=["POST"])
def load_chat():
    data = request.get_json() or {}
    chat = data.get("chat")
    return jsonify({"history": get_messages(chat)})

@app.route("/new_chat", methods=["POST"])
def new_chat():
    new_file = next_chat_file()
    return jsonify({"new_chat": new_file})

# -----------------------------
# 7. RUN
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)