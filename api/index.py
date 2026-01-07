from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
import json
import time

app = Flask(__name__)
# Enable CORS for all domains
CORS(app, resources={r"/*": {"origins": "*"}})

# --- CONFIG ---
JSONBIN_API_KEY = os.environ.get('JSONBIN_API_KEY')
JSONBIN_BIN_ID = os.environ.get('JSONBIN_BIN_ID')
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = "8519835529" 

# --- DATABASE ENGINE (JSONBIN) ---
def get_db():
    if not JSONBIN_API_KEY or not JSONBIN_BIN_ID: 
        print("❌ JSONBin Env Vars Missing")
        return {}
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
        headers = {"X-Master-Key": JSONBIN_API_KEY}
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return res.json().get("record", {})
        print(f"❌ DB Read Error: {res.text}")
        return {}
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return {}

def save_db(data):
    if not JSONBIN_API_KEY or not JSONBIN_BIN_ID: return
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
        headers = {
            "X-Master-Key": JSONBIN_API_KEY,
            "Content-Type": "application/json"
        }
        requests.put(url, headers=headers, json=data)
    except Exception as e:
        print(f"❌ Save Error: {e}")

# --- ROUTES ---

@app.route('/')
def home():
    # Debug info to check if Env vars are loaded
    env_status = {
        "JSONBIN_KEY": "Loaded" if JSONBIN_API_KEY else "Missing",
        "JSONBIN_ID": "Loaded" if JSONBIN_BIN_ID else "Missing",
        "BOT_TOKEN": "Loaded" if TOKEN else "Missing"
    }
    return jsonify({"status": "RiyalNet Backend Live 🚀", "env_check": env_status})

# 1. USER HANDLER
@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    try:
        db = get_db()
        users = db.get("users", {})
        user = users.get(user_id)

        # Global Settings Check
        settings = db.get("settings", {})
        if settings.get("maintenance", False) and str(user_id) != ADMIN_ID:
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 2. ADD BALANCE
@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    try:
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 3. ADMIN ACTIONS
@app.route('/api/admin/action', methods=['POST'])
def admin_action():
    try:
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
            status = req.get('status')
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

        elif action == "send_money":
            target_id = req.get('target_id')
            amount = float(req.get('amount'))
            users = db.get("users", {})
            target = users.get(target_id)
            if target:
                target['balance'] = round(target.get('balance', 0) + amount, 2)
                users[target_id] = target
                db["users"] = users
                save_db(db)
                return jsonify({"status": "Money Sent"})
            return jsonify({"error": "User not found"})

        return jsonify({"error": "Invalid Action"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 4. GET TASKS
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    db = get_db()
    return jsonify(db.get("global_tasks", []))

# 5. WITHDRAWALS
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    try:
        req_data = request.json
        uid = str(req_data.get('user_id'))
        amount = float(req_data.get('amount'))
        
        db = get_db()
        users = db.get("users", {})
        user = users.get(uid)
        
        if not user or user.get('balance', 0) < amount:
            return jsonify({"error": "Insufficient funds"}), 400
        
        user['balance'] = round(user['balance'] - amount, 2)
        users[uid] = user
        
        reqs = db.get("withdrawals", [])
        req_data['status'] = "Pending"
        req_data['date'] = str(time.time())
        reqs.insert(0, req_data)
        db["withdrawals"] = reqs
        db["users"] = users
        save_db(db)
        
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/withdrawals', methods=['GET'])
def get_withdrawals():
    db = get_db()
    return jsonify(db.get("withdrawals", []))

# --- 🔥 WEBHOOK (MOVED UP) 🔥 ---
@app.route('/api/webhook', methods=['POST'])
def webhook():
    if not TOKEN: return "No Token", 200

    data = request.get_json(silent=True)
    if not data or "message" not in data: return "OK"
    
    msg = data["message"]
    chat_id = msg["chat"]["id"]
    
    if "text" in msg:
        text = msg["text"]
        
        if text.startswith("/start"):
            uid = str(msg["from"]["id"])
            first_name = msg["from"].get("first_name", "User")
            
            # Save User
            all_data = get_db()
            users = all_data.get("users", {})
            
            if uid not in users:
                users[uid] = {
                    "user_id": uid, 
                    "first_name": first_name, 
                    "balance": 0.00,
                    "today_ads": 0,
                    "total_ref": 0,
                    "ads_watched_total": 0
                }
                all_data["users"] = users
                save_db(all_data)
            
            # Reply
            payload = {
                "chat_id": chat_id,
                "text": f"👋 Welcome {first_name}!\n\nTap below to start earning:",
                "reply_markup": {
                    "inline_keyboard": [[
                        {"text": "🚀 Open App", "web_app": {"url": "https://net-ui-iota.vercel.app"}}
                    ]]
                }
            }
            try:
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=payload)
            except Exception as e:
                print(f"Telegram API Error: {e}")

    return "OK"

# For Vercel - MUST BE AT THE BOTTOM
if __name__ == '__main__':
    app.run()
