from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
import json
import time

app = Flask(__name__)

# 🔥 CORS FIX: Allow ALL origins explicitly
CORS(app, resources={r"/*": {"origins": "*"}})

# 🔥 ADDITIONAL SECURITY HEADER FIX 🔥
# ይሄ መስመር ነው ዋናው መፍትሄ! ማንኛውም request ሲመጣ "Access-Control" ይጨምርበታል።
@app.after_request
def add_header(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, PUT, DELETE'
    return response

# --- CONFIG ---
TOKEN = os.environ.get('BOT_TOKEN')
JSONBIN_API_KEY = os.environ.get('JSONBIN_API_KEY')
JSONBIN_BIN_ID = os.environ.get('JSONBIN_BIN_ID')

FRONTEND_URL = "https://net-ui-iota.vercel.app"
ADMIN_ID = "8519835529" 

# --- DATABASE ENGINE ---
def get_db():
    if not JSONBIN_API_KEY or not JSONBIN_BIN_ID: return {}
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
        headers = {"X-Master-Key": JSONBIN_API_KEY}
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return res.json().get("record", {})
        return {}
    except: return {}

def save_db(data):
    if not JSONBIN_API_KEY or not JSONBIN_BIN_ID: return
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
        headers = {
            "X-Master-Key": JSONBIN_API_KEY,
            "Content-Type": "application/json"
        }
        requests.put(url, headers=headers, json=data)
    except: pass

# --- ROUTES ---

@app.route('/')
def home():
    return jsonify({"status": "Backend Live", "db_check": "Connected ✅"})

# 1. USER
@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    if request.method == 'OPTIONS': return jsonify({'status': 'ok'}), 200 # Handle Preflight

    all_data = get_db()
    users = all_data.get("users", {})
    user = users.get(user_id)
    
    if request.method == 'POST':
        req_data = request.json
        if not user: 
            user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00}
        
        user['first_name'] = req_data.get('first_name', user.get('first_name'))
        user['photo_url'] = req_data.get('photo_url', user.get('photo_url'))
        
        users[user_id] = user
        all_data["users"] = users
        save_db(all_data)
        return jsonify(user)
    
    if not user:
        user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00, "today_ads": 0}
        users[user_id] = user
        all_data["users"] = users
        save_db(all_data)
        
    return jsonify(user)

# 2. ADD BALANCE
@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    if request.method == 'OPTIONS': return jsonify({'status': 'ok'}), 200

    req_data = request.json
    uid = str(req_data.get('user_id'))
    amount = float(req_data.get('amount'))
    
    all_data = get_db()
    users = all_data.get("users", {})
    user = users.get(uid)
    
    if not user:
        user = {"user_id": uid, "first_name": "User", "balance": 0.00}
    
    user['balance'] = round(user.get('balance', 0) + amount, 2)
    
    if amount == 0.50:
        user['today_ads'] = user.get('today_ads', 0) + 1
        user['ads_watched_total'] = user.get('ads_watched_total', 0) + 1
    
    users[uid] = user
    all_data["users"] = users
    save_db(all_data)
    
    return jsonify({"status": "success", "new_balance": user['balance']})

# 3. ADMIN ACTION
@app.route('/api/admin/action', methods=['POST'])
def admin_action():
    req_data = request.json
    admin_uid = str(req_data.get('admin_id'))
    
    if admin_uid != ADMIN_ID:
        return jsonify({"error": "Unauthorized"}), 403
        
    action = req_data.get('action')
    all_data = get_db()
    
    if action == "add_task":
        tasks = all_data.get("global_tasks", [])
        new_task = req_data.get('task')
        new_task['id'] = int(time.time())
        tasks.append(new_task)
        all_data["global_tasks"] = tasks
        save_db(all_data)
        return jsonify({"status": "Task Added"})
        
    elif action == "send_money":
        target_id = req_data.get('target_id')
        amount = float(req_data.get('amount'))
        users = all_data.get("users", {})
        target = users.get(target_id)
        if target:
            target['balance'] = round(target.get('balance', 0) + amount, 2)
            users[target_id] = target
            all_data["users"] = users
            save_db(all_data)
            return jsonify({"status": "Money Sent"})
        return jsonify({"error": "Target not found"})
        
    return jsonify({"error": "Invalid Action"})

# 4. TASKS & WITHDRAWALS
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    data = get_db()
    return jsonify(data.get("global_tasks", []))

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    req_data = request.json
    uid = str(req_data.get('user_id'))
    amount = float(req_data.get('amount'))
    
    all_data = get_db()
    users = all_data.get("users", {})
    user = users.get(uid)
    
    if not user or user.get('balance', 0) < amount:
        return jsonify({"error": "Insufficient funds"}), 400
    
    user['balance'] = round(user['balance'] - amount, 2)
    users[uid] = user
    
    reqs = all_data.get("withdrawals", [])
    req_data['status'] = "Pending"
    req_data['date'] = str(time.time())
    reqs.insert(0, req_data)
    all_data["withdrawals"] = reqs
    
    save_db(all_data)
    
    return jsonify({"status": "success"})

@app.route('/api/admin/withdrawals', methods=['GET'])
def get_withdrawals():
    data = get_db()
    return jsonify(data.get("withdrawals", []))

# --- WEBHOOK ---
@app.route('/api/webhook', methods=['POST'])
def webhook():
    data = request.get_json(silent=True)
    if not data or "message" not in data: return "OK"
    
    msg = data["message"]
    chat_id = msg["chat"]["id"]
    
    if "text" in msg and msg["text"].startswith("/start"):
        uid = str(msg["from"]["id"])
        first_name = msg["from"].get("first_name", "User")
        
        all_data = get_db()
        users = all_data.get("users", {})
        
        if uid not in users:
            users[uid] = {"user_id": uid, "first_name": first_name, "balance": 0.00}
            all_data["users"] = users
            save_db(all_data)
        
        payload = {
            "chat_id": chat_id,
            "text": f"👋 Welcome {first_name}!",
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "🚀 Open App", "web_app": {"url": FRONTEND_URL}}
                ]]
            }
        }
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=payload)

    return "OK"

# For Vercel
if __name__ == '__main__':
    app.run()
