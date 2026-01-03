from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os
import asyncio
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
ADMIN_ID_NUM = 8519835529 # ያንተ ID ቁጥር

# --- HELPER: Vercel KV ---
def kv_get(key):
    if not KV_URL: return None
    try:
        res = requests.get(f"{KV_URL}/get/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"})
        data = res.json()
        if 'result' in data and data['result']:
            return json.loads(data['result'])
    except: return None
    return None

def kv_set(key, value):
    if not KV_URL: return
    try:
        requests.post(f"{KV_URL}/set/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"}, json=value)
    except: pass

# --- ROUTES ---

@app.route('/')
def home():
    return "RiyalNet Backend is Live! 🚀", 200

# 1. USER DATA (With Photo Update)
@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    if request.method == 'POST':
        # Update User info (Photo, Name)
        data = request.json
        current = kv_get(f"user:{user_id}") or {"user_id": user_id, "balance": 0.00}
        
        current['first_name'] = data.get('first_name', current.get('first_name'))
        current['photo_url'] = data.get('photo_url', current.get('photo_url'))
        
        kv_set(f"user:{user_id}", json.dumps(current))
        return jsonify({"status": "updated"})
        
    else:
        # Get User
        data = kv_get(f"user:{user_id}")
        if data:
            if isinstance(data, str): data = json.loads(data)
            return jsonify(data)
        
        # Auto-Register Guest
        new_user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00, "photo_url": ""}
        kv_set(f"user:{user_id}", json.dumps(new_user))
        return jsonify(new_user)

# 2. ADD MONEY (Admin or Ads)
@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    data = request.json
    uid = str(data.get('user_id'))
    amount = float(data.get('amount'))
    
    current = kv_get(f"user:{uid}")
    if not current: return jsonify({"error": "User not found"}), 404
    if isinstance(current, str): current = json.loads(current)
    
    current['balance'] = float(current.get('balance', 0)) + amount
    kv_set(f"user:{uid}", json.dumps(current))
    
    return jsonify({"status": "success", "new_balance": current['balance']})

# 3. TASKS MANAGEMENT (Admin Adds, Users Get)
@app.route('/api/tasks', methods=['GET', 'POST'])
def handle_tasks():
    if request.method == 'POST':
        # Add Task (Admin Only Logic can be added here)
        new_task = request.json
        new_task['id'] = int(time.time())
        
        tasks = kv_get("global_tasks") or []
        if isinstance(tasks, str): tasks = json.loads(tasks)
        
        tasks.append(new_task)
        kv_set("global_tasks", json.dumps(tasks))
        return jsonify({"status": "Task Added", "tasks": tasks})
        
    else:
        # Get Tasks
        tasks = kv_get("global_tasks") or []
        if isinstance(tasks, str): tasks = json.loads(tasks)
        return jsonify(tasks)

# 4. WITHDRAWAL SYSTEM
@app.route('/api/withdraw', methods=['POST'])
def request_withdraw():
    req = request.json
    uid = req.get('user_id')
    amount = float(req.get('amount'))
    
    # Check Balance
    user = kv_get(f"user:{uid}")
    if isinstance(user, str): user = json.loads(user)
    
    if user['balance'] < amount:
        return jsonify({"error": "Insufficient balance"}), 400
        
    # Deduct Money
    user['balance'] -= amount
    kv_set(f"user:{uid}", json.dumps(user))
    
    # Save Request
    withdrawals = kv_get("withdrawals") or []
    if isinstance(withdrawals, str): withdrawals = json.loads(withdrawals)
    
    req['status'] = 'pending'
    req['date'] = str(time.time())
    withdrawals.append(req)
    kv_set("withdrawals", json.dumps(withdrawals))
    
    return jsonify({"status": "success", "new_balance": user['balance']})

@app.route('/api/admin/withdrawals', methods=['GET'])
def get_withdrawals():
    w = kv_get("withdrawals") or []
    if isinstance(w, str): w = json.loads(w)
    return jsonify(w)

# --- WEBHOOK ---
@app.route('/api/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        application = ApplicationBuilder().token(TOKEN).build()
        
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            u = update.effective_user
            uid = str(u.id)
            
            # Save User with Photo
            # Note: getting photo url via bot api is complex, we do it in Frontend mostly
            if not kv_get(f"user:{uid}"):
                kv_set(f"user:{uid}", json.dumps({"user_id": uid, "first_name": u.first_name, "balance": 0.00}))
            
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
