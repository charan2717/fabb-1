from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.secret_key = "your_secret_key"
socketio = SocketIO(app)

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

# Routes
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

# Route to show profile
@app.route("/profile")
def profile():
    if "username" not in session:
        return redirect(url_for("login"))
    
    username = session["username"]
    with sqlite3.connect("chat.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, bio FROM users WHERE username = ?", (username,))
        user_info = cursor.fetchone()
        if user_info:
            user_info = {"name": user_info[0], "bio": user_info[1]}
        else:
            user_info = {"name": "", "bio": ""}
    
    return render_template("profile.html", user_info=user_info)

# Route to update profile
@app.route("/update_profile", methods=["POST"])
def update_profile():
    if "username" not in session:
        return redirect(url_for("login"))

    data = request.get_json()
    username = session["username"]
    name = data.get("name")
    bio = data.get("bio")
    
    with sqlite3.connect("chat.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET name = ?, bio = ? WHERE username = ?",
                       (name, bio, username))
        conn.commit()
    
    return jsonify({"success": True})



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

@app.route("/search_user", methods=["POST"])
def search_user():
    username = request.json.get("username")
    with sqlite3.connect("chat.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE username LIKE ?", (f"%{username}%",))
        users = cursor.fetchall()
    return jsonify([user[0] for user in users if user[0] != session["username"]])

# WebSocket events
@socketio.on("join")
def handle_join(data):
    room = data["room"]
    username = data["username"]
    join_room(room)
    
    # Retrieve and send past messages
    with sqlite3.connect("chat.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sender, message, timestamp FROM messages WHERE room = ?", (room,))
        messages = cursor.fetchall()
        for message in messages:
            emit("message", {"username": message[0], "message": message[1], "timestamp": message[2]}, room=room)

    emit("message", {"username": "System", "message": f"{username} has joined the room."}, room=room)

@socketio.on("leave")
def handle_leave(data):
    room = data["room"]
    username = data["username"]
    leave_room(room)
    emit("message", {"username": "System", "message": f"{username} has left the room."}, room=room)
    

@socketio.on("send_message")
def handle_send_message(data):
    room = data["room"]
    username = data["username"]
    message = data["message"]

    # Save the message to the database
    with sqlite3.connect("chat.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO messages (room, sender, message) VALUES (?, ?, ?)",
                       (room, username, message))
        conn.commit()

    emit("message", {"username": username, "message": message}, room=room)

@app.route("/logout")
def logout():
    session.pop("username", None)  # Remove the username from the session
    return redirect(url_for("login"))  # Redirect to login page


if __name__ == "__main__":
    socketio.run(app, debug=True)
