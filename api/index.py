from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os
import requests
import json
import time

app = Flask(__name__)
CORS(app)

# --- CONFIG ---
TOKEN = os.environ.get('BOT_TOKEN')
KV_URL = os.environ.get('KV_REST_API_URL')
KV_TOKEN = os.environ.get('KV_REST_API_TOKEN')
FRONTEND_URL = "https://net-ui-iota.vercel.app"
ADMIN_ID = "8519835529"

# --- 🔥 FIXED DB ENGINE (PIPELINE FIX) 🔥 ---
def kv_execute(command, key=None, value=None):
    if not KV_URL or not KV_TOKEN:
        print("❌ KV ENV MISSING")
        return None
    
    try:
        cmd = [command]
        if key is not None:
            cmd.append(key)
        if value is not None:
            # Redis stores strings, so we ensure it's a string
            if isinstance(value, (dict, list)):
                cmd.append(json.dumps(value))
            else:
                cmd.append(str(value))

        # 🔥 FIX 1: Send Raw List (not dict)
        response = requests.post(
            f"{KV_URL}/pipeline",
            headers={"Authorization": f"Bearer {KV_TOKEN}"},
            json=[cmd], 
            timeout=10
        )
        
        data = response.json()
        
        # 🔥 FIX 2: Handle List Response Correctly
        # Upstash returns: [{"result": "OK"}] or [{"result": "JSON_STRING"}]
        if isinstance(data, list) and len(data) > 0:
            item = data[0]
            if "error" in item:
                print(f"❌ Redis Command Error: {item['error']}")
                return None
            
            result = item.get("result")
            
            # If getting data, parse JSON string back to Dict
            if command == "GET" and result and isinstance(result, str):
                try:
                    return json.loads(result)
                except:
                    return result # Return as is if not JSON
            
            return result

    except Exception as e:
        print(f"❌ KV CONNECTION ERROR: {e}")
        return None

# Wrappers
def db_get(key): return kv_execute("GET", key)
def db_set(key, value): return kv_execute("SET", key, value)

# --- ROUTES ---

@app.route('/')
def home():
    # Simple check
    return "RiyalNet Backend Live (DB Fixed) 🚀", 200

# 1. USER
@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    user = db_get(f"user:{user_id}")
    
    if request.method == 'POST':
        data = request.json
        if not user: 
            user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00}
        
        # Update fields
        user['first_name'] = data.get('first_name', user.get('first_name'))
        user['photo_url'] = data.get('photo_url', user.get('photo_url'))
        
        db_set(f"user:{user_id}", user)
        return jsonify(user)
    
    if not user:
        # Auto-create
        user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00, "today_ads": 0}
        db_set(f"user:{user_id}", user)
        
    return jsonify(user)

# 2. ADD BALANCE
@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    data = request.json
    uid = str(data.get('user_id'))
    amount = float(data.get('amount'))
    
    user = db_get(f"user:{uid}")
    if not user:
        user = {"user_id": uid, "first_name": "User", "balance": 0.00}
    
    user['balance'] = round(user.get('balance', 0) + amount, 2)
    
    if amount == 0.50:
        user['today_ads'] = user.get('today_ads', 0) + 1
        user['ads_watched_total'] = user.get('ads_watched_total', 0) + 1
    
    db_set(f"user:{uid}", user)
    return jsonify({"status": "success", "new_balance": user['balance']})

# 3. ADMIN ACTION
@app.route('/api/admin/action', methods=['POST'])
def admin_action():
    data = request.json
    admin_uid = str(data.get('admin_id'))
    
    if admin_uid != ADMIN_ID:
        return jsonify({"error": "Unauthorized"}), 403
        
    action = data.get('action')
    
    if action == "add_task":
        tasks = db_get("global_tasks") or []
        new_task = data.get('task')
        new_task['id'] = int(time.time())
        tasks.append(new_task)
        db_set("global_tasks", tasks)
        return jsonify({"status": "Task Added"})
        
    elif action == "send_money":
        target_id = data.get('target_id')
        amount = float(data.get('amount'))
        target = db_get(f"user:{target_id}")
        if target:
            target['balance'] += amount
            db_set(f"user:{target_id}", target)
            return jsonify({"status": "Money Sent"})
        return jsonify({"error": "Target not found"})
        
    return jsonify({"error": "Invalid Action"})

# 4. TASKS & WITHDRAWALS
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    return jsonify(db_get("global_tasks") or [])

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    uid = str(data.get('user_id'))
    amount = float(data.get('amount'))
    
    user = db_get(f"user:{uid}")
    if not user or user['balance'] < amount:
        return jsonify({"error": "Insufficient funds"}), 400
    
    user['balance'] = round(user['balance'] - amount, 2)
    db_set(f"user:{uid}", user)
    
    reqs = db_get("withdrawals") or []
    data['status'] = "Pending"
    reqs.insert(0, data)
    db_set("withdrawals", reqs)
    
    return jsonify({"status": "success"})

@app.route('/api/admin/withdrawals', methods=['GET'])
def get_withdrawals():
    return jsonify(db_get("withdrawals") or [])

# --- WEBHOOK ---
@app.route('/api/webhook', methods=['POST'])
def webhook():
    data = request.get_json(silent=True)
    if not data or "message" not in data: return "OK"
    
    msg = data["message"]
    chat_id = msg["chat"]["id"]
    uid = str(msg["from"]["id"])
    first_name = msg["from"].get("first_name", "User")
    
    # Save User on Start
    if not db_get(f"user:{uid}"):
        db_set(f"user:{uid}", {"user_id": uid, "first_name": first_name, "balance": 0.00})
    
    # Reply
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
