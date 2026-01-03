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
FRONTEND_URL = "https://net-ui-iota.vercel.app" # ያንተ Frontend Link

# --- 🔥 THE PIPELINE FIX (Database Engine) 🔥 ---
def kv_execute(command, key, value=None):
    if not KV_URL or not KV_TOKEN: return None
    
    try:
        # ትዕዛዙን አዘጋጅ ["SET", "key", "value"] or ["GET", "key"]
        cmd_list = [command, key]
        if value is not None:
            cmd_list.append(json.dumps(value)) # Value must be stringified JSON

        response = requests.post(
            f"{KV_URL}/pipeline",
            headers={
                "Authorization": f"Bearer {KV_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"commands": [cmd_list]}
        )
        
        # Response Parsing (Upstash Pipeline returns list of results)
        data = response.json()
        
        # Extract the result inside the list
        # Result format: [{"result": "..."}]
        if data and isinstance(data, list) and len(data) > 0:
            result = data[0].get("result")
            if result:
                # If it's a GET command, we need to parse the JSON string back to Dict
                if command == "GET":
                    return json.loads(result)
                return result
                
    except Exception as e:
        print(f"KV Error ({command}): {e}")
    
    return None

# Wrappers for easier usage
def db_get(key):
    return kv_execute("GET", key)

def db_set(key, value):
    return kv_execute("SET", key, value)

# --- ROUTES ---

@app.route('/')
def home():
    status = "Connected ✅" if KV_URL else "Disconnected ❌"
    return f"RiyalNet Backend Live. DB Status: {status}", 200

# 1. USER HANDLING
@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    # Fetch User
    user = db_get(f"user:{user_id}")
    
    if request.method == 'POST':
        # Update Request
        req_data = request.json
        if not user: 
            user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00}
        
        # Merge new data
        user.update(req_data)
        db_set(f"user:{user_id}", user)
        return jsonify(user)
    
    # Get Request
    if not user:
        # Auto-create
        user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00}
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
        # Fallback create
        user = {"user_id": uid, "first_name": "User", "balance": 0.00}
    
    # Update Balance
    user['balance'] = round(user.get('balance', 0) + amount, 2)
    
    # Track Ads
    if amount == 0.50:
        user['today_ads'] = user.get('today_ads', 0) + 1
        user['ads_watched_total'] = user.get('ads_watched_total', 0) + 1
    
    # Save using PIPELINE
    db_set(f"user:{uid}", user)
    
    return jsonify({"status": "success", "new_balance": user['balance']})

# 3. TASKS
@app.route('/api/tasks', methods=['GET', 'POST'])
def tasks_route():
    if request.method == 'POST':
        new_task = request.json
        new_task['id'] = int(time.time())
        
        current_tasks = db_get("global_tasks") or []
        current_tasks.append(new_task)
        
        db_set("global_tasks", current_tasks)
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
    
    # Add to withdrawals list
    w_list = db_get("withdrawals") or []
    data['status'] = 'Pending'
    data['date'] = str(time.time())
    w_list.insert(0, data)
    db_set("withdrawals", w_list)
    
    return jsonify({"status": "success", "new_balance": user['balance']})

@app.route('/api/admin/withdrawals', methods=['GET'])
def get_withdrawals():
    return jsonify(db_get("withdrawals") or [])

# --- TELEGRAM BOT WEBHOOK ---
@app.route('/api/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        application = ApplicationBuilder().token(TOKEN).build()
        
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            u = update.effective_user
            uid = str(u.id)
            
            # Register User via Pipeline
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
