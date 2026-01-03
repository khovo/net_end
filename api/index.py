from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os
import requests
import json
import asyncio
import time

app = Flask(__name__)
CORS(app)

# --- CONFIG ---
TOKEN = os.environ.get('BOT_TOKEN')
KV_URL = os.environ.get('KV_REST_API_URL')
KV_TOKEN = os.environ.get('KV_REST_API_TOKEN')
FRONTEND_URL = "https://net-ui-iota.vercel.app"

# --- 🔥 THE FIXED DATABASE ENGINE (PIPELINE) 🔥 ---
def kv_execute(command, key, value=None):
    if not KV_URL or not KV_TOKEN: 
        print("❌ KV Env Vars Missing")
        return None
    
    try:
        # Construct Command
        cmd = [command, key]
        if value is not None:
            cmd.append(json.dumps(value)) # Serialize JSON to string

        # Send Request
        response = requests.post(
            f"{KV_URL}/pipeline",
            headers={
                "Authorization": f"Bearer {KV_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"commands": [cmd]},
            timeout=10
        )
        
        data = response.json()
        
        # ✅ CORRECT PARSING LOGIC (Thanks to ChatGPT fix)
        # Upstash returns: { "result": [ { "result": "..." } ] }
        if "result" in data and len(data["result"]) > 0:
            inner_result = data["result"][0].get("result")
            
            if inner_result is None:
                return None
                
            if command == "GET":
                return json.loads(inner_result) # Parse JSON string back to Dict
            
            return inner_result # For SET, usually returns "OK"
            
    except Exception as e:
        print(f"❌ KV Error ({command}): {e}")
    
    return None

# Wrappers
def db_get(key): return kv_execute("GET", key)
def db_set(key, value): return kv_execute("SET", key, value)

# --- ROUTES ---

@app.route('/')
def home():
    return "RiyalNet Backend Live with FIXED KV Logic! 🚀", 200

# 🔥 DEBUG ENDPOINT (To test DB manually) 🔥
@app.route('/api/debug_kv')
def debug_kv():
    test_data = {"status": "Database is Working!", "time": time.time()}
    db_set("debug:test", test_data)
    result = db_get("debug:test")
    return jsonify(result)

# 1. USER
@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    user = db_get(f"user:{user_id}")
    
    if request.method == 'POST':
        data = request.json
        if not user: 
            user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00}
        user.update(data)
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

# 3. TASKS
@app.route('/api/tasks', methods=['GET', 'POST'])
def tasks_route():
    if request.method == 'POST':
        new_task = request.json
        new_task['id'] = int(time.time())
        current = db_get("global_tasks") or []
        current.append(new_task)
        db_set("global_tasks", current)
        return jsonify({"status": "Task Added"})
    else:
        return jsonify(db_get("global_tasks") or [])

# 4. WITHDRAW
@app.route('/api/withdraw', methods=['POST'])
def withdraw_route():
    data = request.json
    uid = str(data.get('user_id'))
    amount = float(data.get('amount'))
    
    user = db_get(f"user:{uid}")
    if not user or user['balance'] < amount:
        return jsonify({"error": "Insufficient funds"}), 400
    
    user['balance'] = round(user['balance'] - amount, 2)
    db_set(f"user:{uid}", user)
    
    w_list = db_get("withdrawals") or []
    data['status'] = 'Pending'
    data['date'] = str(time.time())
    w_list.insert(0, data)
    db_set("withdrawals", w_list)
    
    return jsonify({"status": "success", "new_balance": user['balance']})

@app.route('/api/admin/withdrawals', methods=['GET'])
def get_withdrawals():
    return jsonify(db_get("withdrawals") or [])

# --- WEBHOOK ---
@app.route('/api/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        application = ApplicationBuilder().token(TOKEN).build()
        
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            u = update.effective_user
            uid = str(u.id)
            
            if not db_get(f"user:{uid}"):
                db_set(f"user:{uid}", {"user_id": uid, "first_name": u.first_name, "balance": 0.00})
            
            btn = InlineKeyboardButton("🚀 Open App", web_app=WebAppInfo(url=FRONTEND_URL))
            await update.message.reply_text(f"Welcome {u.first_name}!", reply_markup=InlineKeyboardMarkup([[btn]]))

        application.add_handler(CommandHandler("start", start))
        
        async def runner():
            await application.initialize()
            update = Update.de_json(request.get_json(force=True), application.bot)
            await application.process_update(update)
            await application.shutdown()
            
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(runner())
        return "OK"
    return "Error"
