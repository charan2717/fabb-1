from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.secret_key = "your_secret_key"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Database setup
def init_db():
    with sqlite3.connect("chat.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room TEXT NOT NULL,
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

init_db()

# User authentication routes
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        with sqlite3.connect("chat.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            if user and check_password_hash(user[2], password):
                session["username"] = username
                return redirect(url_for("chat"))
            else:
                return "Invalid credentials"
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        with sqlite3.connect("chat.db") as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                               (username, generate_password_hash(password)))
                conn.commit()
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                return "Username already exists"
    return render_template("register.html")

@app.route("/chat")
def chat():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("chat.html", username=session["username"])

# WebSocket events
@socketio.on("join")
def handle_join(data):
    room = data["room"]
    username = session.get("username")
    if username:
        join_room(room)
        emit("message", {"username": "System", "message": f"{username} has joined the room."}, room=room)

@socketio.on("send_message")
def handle_send_message(data):
    room = data["room"]
    username = session.get("username")
    message = data["message"]

    if username:
        # Save the message to the database
        with sqlite3.connect("chat.db") as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO messages (room, sender, message) VALUES (?, ?, ?)",
                           (room, username, message))
            conn.commit()

        # Emit the message to the room
        emit("message", {"username": username, "message": message}, room=room)

@socketio.on("leave")
def handle_leave(data):
    room = data["room"]
    username = session.get("username")
    if username:
        leave_room(room)
        emit("message", {"username": "System", "message": f"{username} has left the room."}, room=room)

@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    socketio.run(app, debug=True)
