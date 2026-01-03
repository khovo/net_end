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
CORS(app) # 🔥 ይሄ ነው Frontend እንዲገባ የሚፈቅደው!

# --- CONFIG ---
TOKEN = os.environ.get('BOT_TOKEN')
KV_URL = os.environ.get('KV_REST_API_URL')
KV_TOKEN = os.environ.get('KV_REST_API_TOKEN')
FRONTEND_URL = "https://net-ui-iota.vercel.app"

# --- HELPER ---
def kv_get(key):
    if not KV_URL or not KV_TOKEN: return None
    try:
        res = requests.get(f"{KV_URL}/get/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"})
        data = res.json()
        if 'result' in data and data['result']:
            return json.loads(data['result'])
    except: return None
    return None

def kv_set(key, value):
    if not KV_URL or not KV_TOKEN: return
    try:
        requests.post(f"{KV_URL}/set/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"}, json=value)
    except: pass

# --- ROUTES ---
@app.route('/')
def home():
    status = "Connected ✅" if KV_URL else "Not Connected ❌ (Check Vercel Envs)"
    return f"Backend Live. Database: {status}", 200

@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    # Get or Create User
    user = kv_get(f"user:{user_id}")
    if not user:
        user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00}
        kv_set(f"user:{user_id}", json.dumps(user))
    
    if request.method == 'POST':
        # Update Info from Frontend
        data = request.json
        user['first_name'] = data.get('first_name', user['first_name'])
        user['photo_url'] = data.get('photo_url', user.get('photo_url', ''))
        kv_set(f"user:{user_id}", json.dumps(user))
    
    return jsonify(user)

@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    data = request.json
    uid = str(data.get('user_id'))
    amount = float(data.get('amount'))
    
    user = kv_get(f"user:{uid}")
    if not user: 
        user = {"user_id": uid, "first_name": "User", "balance": 0.00}
    
    user['balance'] = round(user.get('balance', 0) + amount, 2)
    # Track Ad Count
    if amount == 0.50:
        user['today_ads'] = user.get('today_ads', 0) + 1
        user['ads_watched_total'] = user.get('ads_watched_total', 0) + 1

    kv_set(f"user:{uid}", json.dumps(user))
    return jsonify({"status": "success", "new_balance": user['balance']})

# --- TELEGRAM BOT ---
@app.route('/api/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        application = ApplicationBuilder().token(TOKEN).build()
        
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            u = update.effective_user
            uid = str(u.id)
            
            # Register User on Start
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
