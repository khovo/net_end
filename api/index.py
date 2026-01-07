from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
import json
import time

app = Flask(__name__)
CORS(app)

# --- CONFIG ---
# Vercel Environment Variables ላይ ማስገባት እንዳትረሳ!
JSONBIN_API_KEY = os.environ.get('JSONBIN_API_KEY')
JSONBIN_BIN_ID = os.environ.get('JSONBIN_BIN_ID')
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = "8519835529" # ያንተ ID

# --- DATABASE ENGINE (JSONBIN) ---
def get_db():
    if not JSONBIN_API_KEY or not JSONBIN_BIN_ID: return {}
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
        headers = {"X-Master-Key": JSONBIN_API_KEY}
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            # 🔥 FIX: .get("record") መረጃውን ከውስጥ ለማውጣት ወሳኝ ነው
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
    return "RiyalNet JSONBin Backend Live 🚀", 200

# 1. USER HANDLER
@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    db = get_db()
    users = db.get("users", {})
    user = users.get(user_id)

    # Global Settings Check (Maintenance)
    settings = db.get("settings", {})
    if settings.get("maintenance", False) and user_id != ADMIN_ID:
        return jsonify({"error": "MAINTENANCE"}), 503

    # Ban Check
    if user and user.get("banned", False):
        return jsonify({"error": "BANNED"}), 403

    if request.method == 'POST':
        data = request.json
        if not user: 
            user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00}
        
        # Update Info
        user['first_name'] = data.get('first_name', user.get('first_name'))
        user['photo_url'] = data.get('photo_url', user.get('photo_url'))
        
        users[user_id] = user
        db["users"] = users
        save_db(db)
        return jsonify(user)
    
    if not user:
        # Auto-create
        user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00, "today_ads": 0, "banned": False}
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
    
    user['balance'] = round(user.get('balance', 0) + amount, 2)
    
    if amount == 0.50:
        user['today_ads'] = user.get('today_ads', 0) + 1
        user['ads_watched_total'] = user.get('ads_watched_total', 0) + 1
        
    users[uid] = user
    db["users"] = users
    save_db(db)
    
    return jsonify({"status": "success", "new_balance": user['balance']})

# 3. ADMIN ACTIONS (Tasks, Ban, Maintenance)
@app.route('/api/admin/action', methods=['POST'])
def admin_action():
    req = request.json
    if str(req.get('admin_id')) != ADMIN_ID:
        return jsonify({"error": "Unauthorized"}), 403
        
    action = req.get('action')
    db = get_db()
    
    if action == "add_task":
        tasks = db.get("global_tasks", [])
        new_task = req.get('task')
        new_task['id'] = int(time.time())
        tasks.append(new_task)
        db["global_tasks"] = tasks
        save_db(db)
        return jsonify({"status": "Task Added"})

    elif action == "delete_task":
        tid = req.get('task_id')
        tasks = db.get("global_tasks", [])
        db["global_tasks"] = [t for t in tasks if t.get('id') != tid]
        save_db(db)
        return jsonify({"status": "Task Deleted"})

    elif action == "ban_user":
        target = req.get('target_id')
        status = req.get('status') # True/False
        users = db.get("users", {})
        if target in users:
            users[target]['banned'] = status
            db["users"] = users
            save_db(db)
            return jsonify({"status": "Updated"})
            
    elif action == "maintenance":
        status = req.get('status')
        db["settings"] = {"maintenance": status}
        save_db(db)
        return jsonify({"status": "Updated"})

    return jsonify({"error": "Invalid Action"})

# 4. GET TASKS
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    db = get_db()
    return jsonify(db.get("global_tasks", []))

# 5. WITHDRAWALS
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    uid = str(data.get('user_id'))
    amount = float(data.get('amount'))
    
    db = get_db()
    users = db.get("users", {})
    user = users.get(uid)
    
    if not user or user.get('balance', 0) < amount:
        return jsonify({"error": "Insufficient funds"}), 400
        
    user['balance'] = round(user['balance'] - amount, 2)
    users[uid] = user
    
    w_list = db.get("withdrawals", [])
    data['status'] = "Pending"
    w_list.insert(0, data)
    db["withdrawals"] = w_list
    db["users"] = users
    save_db(db)
    
    return jsonify({"status": "success"})

# For Vercel
if __name__ == '__main__':
    app.run()
