from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os
import asyncio
import requests
import json
import urllib.parse  # 🔥 አዲሱ እና ወሳኙ መፍትሄ 🔥

app = Flask(__name__)
CORS(app)

# --- CONFIG ---
TOKEN = os.environ.get('BOT_TOKEN')
KV_URL = os.environ.get('KV_REST_API_URL')
KV_TOKEN = os.environ.get('KV_REST_API_TOKEN')
FRONTEND_URL = "https://net-ui-iota.vercel.app"

# --- HELPER: Vercel KV (THE FIX) ---
def db_read(key):
    if not KV_URL or not KV_TOKEN: return None
    try:
        # GET request ትክክል ነበር
        res = requests.get(f"{KV_URL}/get/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"})
        data = res.json()
        if 'result' in data and data['result']:
            # Redis string ስለሚመልስ ወደ JSON እንቀይረዋለን
            return json.loads(data['result'])
    except: return None
    return None

def db_write(key, value):
    if not KV_URL or not KV_TOKEN: return
    try:
        # 🔥 THE FIX: Value ወደ String ቀይሮ URL Encode ማድረግ 🔥
        val_str = json.dumps(value) 
        encoded_val = urllib.parse.quote(val_str)
        
        # ትክክለኛው የ Vercel KV አጻጻፍ: /set/key/value
        url = f"{KV_URL}/set/{key}/{encoded_val}"
        
        requests.post(url, headers={"Authorization": f"Bearer {KV_TOKEN}"})
    except Exception as e:
        print(f"DB Error: {e}")

# --- ROUTES ---

@app.route('/')
def home():
    return "Backend is Running & Database is Fixed! 🚀", 200

@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    # 1. Get User
    user = db_read(f"user:{user_id}")
    
    # 2. Auto-Create if not exists
    if not user:
        user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00, "today_ads": 0}
        db_write(f"user:{user_id}", user)
    
    # 3. Update (POST)
    if request.method == 'POST':
        data = request.json
        # Merge old and new data
        user.update(data)
        db_write(f"user:{user_id}", user)
    
    return jsonify(user)

@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    data = request.json
    uid = str(data.get('user_id'))
    amount = float(data.get('amount'))
    
    # Get User
    user = db_read(f"user:{uid}")
    
    if not user:
        # Fallback create
        user = {"user_id": uid, "first_name": "User", "balance": 0.00}
    
    # Update Balance
    user['balance'] = round(user.get('balance', 0) + amount, 2)
    
    # Track Ads
    if amount == 0.50:
        user['today_ads'] = user.get('today_ads', 0) + 1
        user['ads_watched_total'] = user.get('ads_watched_total', 0) + 1

    # Save
    db_write(f"user:{uid}", user)
    
    return jsonify({"status": "success", "new_balance": user['balance']})

# --- WEBHOOK ---
@app.route('/api/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        application = ApplicationBuilder().token(TOKEN).build()
        
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            u = update.effective_user
            uid = str(u.id)
            
            # Save User on /start
            if not db_read(f"user:{uid}"):
                db_write(f"user:{uid}", {"user_id": uid, "first_name": u.first_name, "balance": 0.00})
            
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
