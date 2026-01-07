from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os
import requests
import json
import time

app = Flask(__name__)
CORS(app)

# --- CONFIG ---
TOKEN = os.environ.get('BOT_TOKEN')
JSONBIN_API_KEY = os.environ.get('JSONBIN_API_KEY')
JSONBIN_BIN_ID = os.environ.get('JSONBIN_BIN_ID')
FRONTEND_URL = "https://net-ui-iota.vercel.app"
ADMIN_ID = "8519835529"

# --- JSONBIN ENGINE ---
def get_db():
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
        headers = {"X-Master-Key": JSONBIN_API_KEY}
        res = requests.get(url, headers=headers)
        return res.json().get("record", {}) if res.status_code == 200 else {}
    except: return {}

def save_db(data):
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
        headers = {"X-Master-Key": JSONBIN_API_KEY, "Content-Type": "application/json"}
        requests.put(url, headers=headers, json=data)
    except: pass

# --- MIDDLEWARE CHECKS ---
def check_global_status(db):
    settings = db.get("settings", {"maintenance": False})
    return settings.get("maintenance", False)

# --- ROUTES ---

@app.route('/')
def home():
    return "RiyalNet v2.0 Live 🚀", 200

# 1. USER HANDLER (Checks Ban & Maintenance)
@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    db = get_db()
    
    # 1. Check Maintenance (Admin is excluded)
    if check_global_status(db) and user_id != ADMIN_ID:
        return jsonify({"error": "MAINTENANCE_MODE", "message": "Bot is currently updating..."}), 503

    users = db.get("users", {})
    user = users.get(user_id)

    # 2. Check Ban
    if user and user.get("is_banned", False):
        return jsonify({"error": "BANNED", "message": "Your account has been banned."}), 403

    if request.method == 'POST':
        data = request.json
        if not user: 
            user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00, "is_banned": False}
        
        user['first_name'] = data.get('first_name', user.get('first_name'))
        user['photo_url'] = data.get('photo_url', user.get('photo_url'))
        
        users[user_id] = user
        db["users"] = users
        save_db(db)
        return jsonify(user)
    
    if not user:
        user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00, "today_ads": 0, "is_banned": False}
        users[user_id] = user
        db["users"] = users
        save_db(db)
        
    return jsonify(user)

# 2. ADD BALANCE
@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    data = request.json
    uid = str(data.get('user_id'))
    amount = float(data.get('amount'))
    
    db = get_db()
    users = db.get("users", {})
    user = users.get(uid)
    
    if not user: return jsonify({"error": "User not found"}), 404
    if user.get("is_banned"): return jsonify({"error": "Banned"}), 403

    user['balance'] = round(user.get('balance', 0) + amount, 2)
    
    if amount == 0.50:
        user['today_ads'] = user.get('today_ads', 0) + 1
        user['ads_watched_total'] = user.get('ads_watched_total', 0) + 1
    
    users[uid] = user
    db["users"] = users
    save_db(db)
    
    return jsonify({"status": "success", "new_balance": user['balance']})

# 3. ADMIN ACTIONS (Ban, Maintenance, Tasks)
@app.route('/api/admin/action', methods=['POST'])
def admin_action():
    req_data = request.json
    if str(req_data.get('admin_id')) != ADMIN_ID:
        return jsonify({"error": "Unauthorized"}), 403
        
    action = req_data.get('action')
    db = get_db()
    
    # A. Add Task
    if action == "add_task":
        tasks = db.get("global_tasks", [])
        new_task = req_data.get('task')
        new_task['id'] = int(time.time()) # Unique ID
        tasks.append(new_task)
        db["global_tasks"] = tasks
        save_db(db)
        return jsonify({"status": "Task Added"})

    # B. Delete Task
    elif action == "delete_task":
        task_id = req_data.get('task_id')
        tasks = db.get("global_tasks", [])
        # Filter out the deleted task
        db["global_tasks"] = [t for t in tasks if t.get('id') != task_id]
        save_db(db)
        return jsonify({"status": "Task Deleted"})

    # C. Ban/Unban User
    elif action == "ban_user":
        target_id = req_data.get('target_id')
        status = req_data.get('status') # True/False
        users = db.get("users", {})
        if target_id in users:
            users[target_id]['is_banned'] = status
            db["users"] = users
            save_db(db)
            return jsonify({"status": f"User Banned: {status}"})
        return jsonify({"error": "User not found"})

    # D. Maintenance Mode
    elif action == "toggle_maintenance":
        status = req_data.get('status')
        db["settings"] = {"maintenance": status}
        save_db(db)
        return jsonify({"status": f"Maintenance: {status}"})

    return jsonify({"error": "Invalid Action"})

# 4. GET TASKS
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    db = get_db()
    return jsonify(db.get("global_tasks", []))

# --- WEBHOOK ---
@app.route('/api/webhook', methods=['POST'])
def webhook():
    data = request.get_json(silent=True)
    if not data or "message" not in data: return "OK"
    
    msg = data["message"]
    chat_id = msg["chat"]["id"]
    uid = str(msg["from"]["id"])
    first_name = msg["from"].get("first_name", "User")
    
    # Check Maintenance for Bot messages too
    db = get_db()
    if check_global_status(db) and uid != ADMIN_ID:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
            "chat_id": chat_id, "text": "🚧 Bot is under maintenance. Please try again later."
        })
        return "OK"

    # Save User
    users = db.get("users", {})
    if uid not in users:
        users[uid] = {"user_id": uid, "first_name": first_name, "balance": 0.00, "is_banned": False}
        db["users"] = users
        save_db(db)
    
    # Reply
    payload = {
        "chat_id": chat_id,
        "text": f"👋 Welcome {first_name}!",
        "reply_markup": {
            "inline_keyboard": [[{"text": "🚀 Open App", "web_app": {"url": FRONTEND_URL}}]]
        }
    }
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=payload)
    return "OK"
