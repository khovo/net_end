from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
import json
import time

app = Flask(__name__)

# --- CORS & SECURITY HEADERS ---
# Allow all origins for simplicity in this setup
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def add_header(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, PUT, DELETE'
    return response

# --- CONFIGURATION ---
TOKEN = os.environ.get('BOT_TOKEN')
JSONBIN_API_KEY = os.environ.get('JSONBIN_API_KEY')
JSONBIN_BIN_ID = os.environ.get('JSONBIN_BIN_ID')
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
    return jsonify({"status": "Backend Live", "message": "RiyalNet API Ready 🚀"})

# 1. USER SYNC
@app.route('/api/user/<user_id>', methods=['POST'])
def handle_user(user_id):
    req_data = request.json
    all_data = get_db()
    
    # Check Maintenance Mode
    if all_data.get("maintenance_mode", False) and user_id != ADMIN_ID:
        return jsonify({"error": "Maintenance Mode On", "maintenance": True}), 503

    users = all_data.get("users", {})
    user = users.get(user_id)
    
    # Create or Update
    if not user:
        user = {
            "user_id": user_id, 
            "first_name": req_data.get('first_name', 'Guest'),
            "balance": 0.00,
            "ads_watched_total": 0,
            "today_ads": 0,
            "joined_at": time.time(),
            "banned": False
        }
    
    # Update latest info
    user['first_name'] = req_data.get('first_name', user.get('first_name'))
    user['photo_url'] = req_data.get('photo_url', user.get('photo_url'))
    
    # Save
    users[user_id] = user
    all_data["users"] = users
    save_db(all_data)
    
    # Return user data + global config
    return jsonify({
        "user": user,
        "tasks": all_data.get("global_tasks", []),
        "maintenance": False
    })

# 2. EARNING (ADS/TASKS)
@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    req_data = request.json
    uid = str(req_data.get('user_id'))
    amount = float(req_data.get('amount'))
    
    all_data = get_db()
    users = all_data.get("users", {})
    user = users.get(uid)
    
    if not user: return jsonify({"error": "User not found"}), 404
    if user.get("banned", False): return jsonify({"error": "User is Banned"}), 403

    # Update Balance
    user['balance'] = round(user.get('balance', 0) + amount, 2)
    
    # Track Ad Stats
    if amount == 0.50: # Assuming 0.50 is ad reward
        user['today_ads'] = user.get('today_ads', 0) + 1
        user['ads_watched_total'] = user.get('ads_watched_total', 0) + 1
        
    users[uid] = user
    all_data["users"] = users
    save_db(all_data)
    
    return jsonify({"status": "success", "new_balance": user['balance']})

# 3. WITHDRAWAL REQUEST
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    req_data = request.json
    uid = str(req_data.get('user_id'))
    amount = float(req_data.get('amount'))
    
    all_data = get_db()
    users = all_data.get("users", {})
    user = users.get(uid)
    
    if not user: return jsonify({"error": "User not found"}), 404
    if user.get("banned", False): return jsonify({"error": "Banned"}), 403
    if user.get('balance', 0) < amount: return jsonify({"error": "Insufficient funds"}), 400
    
    # Deduct Balance Immediately
    user['balance'] = round(user['balance'] - amount, 2)
    users[uid] = user
    
    # Create Request Record
    withdrawals = all_data.get("withdrawals", [])
    new_req = {
        "id": int(time.time()),
        "user_id": uid,
        "amount": amount,
        "account": req_data.get('account'),
        "method": req_data.get('method', 'Telebirr'),
        "status": "Pending",
        "date": time.ctime()
    }
    withdrawals.insert(0, new_req) # Add to top
    
    all_data["withdrawals"] = withdrawals
    all_data["users"] = users
    save_db(all_data)
    
    return jsonify({"status": "success", "message": "Request Sent"})

# 4. ADMIN PANEL ACTIONS
@app.route('/api/admin/action', methods=['POST'])
def admin_action():
    req_data = request.json
    admin_uid = str(req_data.get('admin_id'))
    
    if admin_uid != ADMIN_ID: return jsonify({"error": "Unauthorized"}), 403
    
    action = req_data.get('action')
    all_data = get_db()
    
    # --- TOGGLE MAINTENANCE ---
    if action == "toggle_maintenance":
        current = all_data.get("maintenance_mode", False)
        all_data["maintenance_mode"] = not current
        save_db(all_data)
        return jsonify({"status": "Updated", "mode": all_data["maintenance_mode"]})
        
    # --- BAN USER ---
    elif action == "ban_user":
        target_id = req_data.get('target_id')
        users = all_data.get("users", {})
        if target_id in users:
            users[target_id]['banned'] = not users[target_id].get('banned', False)
            all_data["users"] = users
            save_db(all_data)
            return jsonify({"status": "Banned/Unbanned", "is_banned": users[target_id]['banned']})
            
    # --- WITHDRAWAL ACTION ---
    elif action == "handle_withdrawal":
        req_id = req_data.get('req_id')
        decision = req_data.get('decision') # 'Approved' or 'Rejected'
        withdrawals = all_data.get("withdrawals", [])
        
        for w in withdrawals:
            if w['id'] == req_id:
                w['status'] = decision
                # If rejected, refund money
                if decision == "Rejected":
                    users = all_data.get("users", {})
                    if w['user_id'] in users:
                        users[w['user_id']]['balance'] += w['amount']
                        all_data["users"] = users
                break
        all_data["withdrawals"] = withdrawals
        save_db(all_data)
        return jsonify({"status": "Processed"})

    # --- ADD TASK ---
    elif action == "add_task":
        tasks = all_data.get("global_tasks", [])
        new_task = req_data.get('task')
        new_task['id'] = int(time.time())
        tasks.append(new_task)
        all_data["global_tasks"] = tasks
        save_db(all_data)
        return jsonify({"status": "Task Added"})
    
    # --- GET ALL DATA ---
    elif action == "get_full_data":
        return jsonify(all_data)

    return jsonify({"error": "Invalid Action"})

# --- TELEGRAM WEBHOOK ---
@app.route('/api/webhook', methods=['POST'])
def webhook():
    # Basic logic to reply to /start
    data = request.get_json(silent=True)
    if data and "message" in data:
        msg = data["message"]
        if "text" in msg and msg["text"].startswith("/start"):
            chat_id = msg["chat"]["id"]
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                "chat_id": chat_id,
                "text": "👋 Welcome to RiyalNet! Watch ads & Earn ETB.",
                "reply_markup": {
                    "inline_keyboard": [[{"text": "💸 Start Earning", "web_app": {"url": "https://net-ui-iota.vercel.app"}}]]
                }
            })
    return "OK"

if __name__ == '__main__':
    app.run()
