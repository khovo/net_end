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
KV_URL = os.environ.get('KV_REST_API_URL')
KV_TOKEN = os.environ.get('KV_REST_API_TOKEN')
FRONTEND_URL = "https://net-ui-iota.vercel.app"

# --- 🔥 ROBUST DATABASE ENGINE 🔥 ---
def run_kv_command(command, *args):
    """
    Standard way to talk to Vercel KV (Upstash Redis)
    Sends ["SET", "key", "value"] directly.
    """
    if not KV_URL or not KV_TOKEN:
        print("❌ DB Error: Missing Env Vars")
        return None
    
    try:
        payload = [command] + list(args)
        response = requests.post(
            KV_URL, # Base URL
            headers={"Authorization": f"Bearer {KV_TOKEN}"},
            json=payload
        )
        data = response.json()
        
        # Check for Redis Errors
        if 'error' in data:
            print(f"❌ Redis Error: {data['error']}")
            return None
            
        return data.get('result')
    except Exception as e:
        print(f"❌ Request Error: {e}")
        return None

# Helpers
def db_get(key):
    result = run_kv_command("GET", key)
    if result:
        return json.loads(result) # Redis stores strings, we convert back to JSON
    return None

def db_set(key, value):
    # Convert JSON object to String before saving
    value_str = json.dumps(value)
    return run_kv_command("SET", key, value_str)

# --- ROUTES ---

@app.route('/')
def home():
    # Test DB Connection on Home Page
    test = run_kv_command("PING")
    status = "Connected ✅" if test == "PONG" else "Disconnected ❌ (Check Vercel Envs)"
    return f"Backend Live. Database Status: {status}", 200

# 1. USER HANDLING
@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    user = db_get(f"user:{user_id}")
    
    if request.method == 'POST':
        # Update Info
        data = request.json
        if not user: user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00}
        
        # Merge updates
        user['first_name'] = data.get('first_name', user.get('first_name'))
        user['photo_url'] = data.get('photo_url', user.get('photo_url'))
        
        db_set(f"user:{user_id}", user)
        return jsonify(user)
    
    if not user:
        # Create New
        user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00, "today_ads": 0}
        db_set(f"user:{user_id}", user)
        
    return jsonify(user)

# 2. ADD BALANCE (Atomic Logic)
@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    try:
        data = request.json
        uid = str(data.get('user_id'))
        amount = float(data.get('amount'))
        
        user = db_get(f"user:{uid}")
        if not user:
            user = {"user_id": uid, "first_name": "User", "balance": 0.00}
        
        # Update Balance
        user['balance'] = round(user.get('balance', 0) + amount, 2)
        
        # Track Ads
        if amount == 0.50:
            user['today_ads'] = user.get('today_ads', 0) + 1
            user['ads_watched_total'] = user.get('ads_watched_total', 0) + 1
            
        # 🔥 SAVE TO DB (CRITICAL STEP) 🔥
        save_result = db_set(f"user:{uid}", user)
        
        if save_result == "OK":
            return jsonify({"status": "success", "new_balance": user['balance']})
        else:
            return jsonify({"error": "Failed to save to DB"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 3. TASKS
@app.route('/api/tasks', methods=['GET', 'POST'])
def tasks():
    if request.method == 'POST':
        new_task = request.json
        new_task['id'] = int(time.time())
        
        tasks = db_get("global_tasks") or []
        tasks.append(new_task)
        
        db_set("global_tasks", tasks)
        return jsonify({"status": "Task Added"})
    else:
        return jsonify(db_get("global_tasks") or [])

# 4. WITHDRAWAL
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
    
    # Save Request
    reqs = db_get("withdrawals") or []
    data['status'] = 'Pending'
    data['date'] = str(time.time())
    reqs.insert(0, data)
    db_set("withdrawals", reqs)
    
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
            
            # Register User if new
            if not db_get(f"user:{uid}"):
                db_set(f"user:{uid}", {"user_id": uid, "first_name": u.first_name, "balance": 0.00})
            
            btn = InlineKeyboardButton("🚀 Open App", web_app={"url": FRONTEND_URL})
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
