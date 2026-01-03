from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os
import requests
import json
import asyncio

app = Flask(__name__)
# 🔥 ወሳኝ ማስተካከያ: ማንኛውም Frontend እንዲያገኘው ፍቀድ 🔥
CORS(app, resources={r"/*": {"origins": "*"}})

# --- CONFIG ---
TOKEN = os.environ.get('BOT_TOKEN')
KV_URL = os.environ.get('KV_REST_API_URL')
KV_TOKEN = os.environ.get('KV_REST_API_TOKEN')
FRONTEND_URL = "https://net-ui-iota.vercel.app" # ያንተን UI ሊንክ እዚህ አስገባ

# --- HELPER ---
def db_req(method, key, value=None):
    if not KV_URL or not KV_TOKEN: return None
    try:
        url = f"{KV_URL}/{method}/{key}"
        headers = {"Authorization": f"Bearer {KV_TOKEN}"}
        if method == "set":
            requests.post(url, headers=headers, json=value)
        else:
            res = requests.get(url, headers=headers)
            data = res.json()
            if 'result' in data and data['result']:
                return json.loads(data['result'])
    except Exception as e:
        print(f"DB Error: {e}")
    return None

# --- ROUTES ---
@app.route('/')
def home():
    # Browser ላይ ሲከፈት እንዲታወቅ
    status = "Connected ✅" if KV_URL else "Not Configured ❌"
    return jsonify({"status": "Backend Live", "database": status})

@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    # 1. Get User
    user = db_req("get", f"user:{user_id}")
    
    if not user:
        # Auto-create if not exists
        user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00}
        db_req("set", f"user:{user_id}", json.dumps(user))
    
    # 2. Update (POST)
    if request.method == 'POST':
        data = request.json
        user.update(data)
        db_req("set", f"user:{user_id}", json.dumps(user))
    
    return jsonify(user)

@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    data = request.json
    uid = str(data.get('user_id'))
    amount = float(data.get('amount'))
    
    user = db_req("get", f"user:{uid}")
    if user:
        user['balance'] = round(user.get('balance', 0) + amount, 2)
        db_req("set", f"user:{uid}", json.dumps(user))
        return jsonify({"status": "success", "new_balance": user['balance']})
    
    return jsonify({"error": "User not found"}), 404

# --- WEBHOOK (Start Command) ---
@app.route('/api/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        application = ApplicationBuilder().token(TOKEN).build()
        
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            u = update.effective_user
            uid = str(u.id)
            # Create user on /start
            if not db_req("get", f"user:{uid}"):
                db_req("set", f"user:{uid}", json.dumps({"user_id": uid, "first_name": u.first_name, "balance": 0.00}))
            
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
