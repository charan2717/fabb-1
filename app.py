from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore

# Firebase initialization
cred = credentials.Certificate("ffff-fe87d-firebase-adminsdk-fbsvc-9fec405662.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

app = Flask(__name__)
app.secret_key = "your_secret_key"
socketio = SocketIO(app)
CORS(app)

# Routes
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user_ref = db.collection("users").document(username)
        user = user_ref.get()
        if user.exists and check_password_hash(user.to_dict()["password"], password):
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
    user_ref = db.collection("users").document(username)
    user_info = user_ref.get().to_dict()
    user_info = user_info if user_info else {"name": "", "bio": ""}

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

    user_ref = db.collection("users").document(username)
    user_ref.update({"name": name, "bio": bio})

    return jsonify({"success": True})

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user_ref = db.collection("users").document(username)
        if user_ref.get().exists:
            return "Username already exists"

        user_ref.set({
            "password": generate_password_hash(password),
            "name": "",
            "bio": ""
        })

        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/chat")
def chat():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("chat.html", username=session["username"])

@app.route("/search_user", methods=["POST"])
def search_user():
    username = request.json.get("username")
    users_ref = db.collection("users")
    users = [doc.id for doc in users_ref.stream() if username.lower() in doc.id.lower() and doc.id != session["username"]]
    return jsonify(users)

# WebSocket events
@socketio.on("join")
def handle_join(data):
    room = data["room"]
    username = data["username"]
    join_room(room)

    # Retrieve and send past messages
    messages_ref = db.collection("messages").where("room", "==", room).order_by("timestamp")
    for message in messages_ref.stream():
        msg_data = message.to_dict()
        emit("message", {"username": msg_data["sender"], "message": msg_data["message"], "timestamp": msg_data.get("timestamp")}, room=room)

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

    # Save the message to the Firestore
    db.collection("messages").add({
        "room": room,
        "sender": username,
        "message": message,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    emit("message", {"username": username, "message": message}, room=room)

@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    socketio.run(app, debug=True)
