from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os
import asyncio
import requests
import json

app = Flask(__name__)
CORS(app) # ይሄ Frontend እና Backend እንዲግባቡ ይፈቅዳል (ወሳኝ ነው!)

# 🔥 CONFIGURATION 🔥
TOKEN = os.environ.get('BOT_TOKEN')
KV_URL = os.environ.get('KV_REST_API_URL')
KV_TOKEN = os.environ.get('KV_REST_API_TOKEN')

# ⚠️ የ FRONTEND ሊንክ (Frontendን Deploy ካደረግክ በኋላ እዚህ ትሞላዋለህ)
FRONTEND_URL = "https://net-ui-iota.vercel.app" 

# Helper: Vercel KV
def kv_set(key, value):
    requests.post(f"{KV_URL}/set/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"}, json=value)

def kv_get(key):
    res = requests.get(f"{KV_URL}/get/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"})
    try:
        data = res.json()
        if 'result' in data and data['result']:
            return json.loads(data['result'])
    except:
        return None
    return None

# --- BOT LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    
    # Save User to DB
    if not kv_get(f"user:{uid}"):
        kv_set(f"user:{uid}", json.dumps({"balance": 0.00, "name": user.first_name}))

    # Link to Frontend
    btn = InlineKeyboardButton("🚀 Open App", web_app={"url": FRONTEND_URL})
    await update.message.reply_text("Welcome to RiyalNet!", reply_markup=InlineKeyboardMarkup([[btn]]))

# --- WEBHOOK ---
@app.route('/api/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        application = ApplicationBuilder().token(TOKEN).build()
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

# --- API FOR FRONTEND ---
@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    data = request.json
    uid = str(data.get('user_id'))
    amount = data.get('amount')
    
    current = kv_get(f"user:{uid}")
    if isinstance(current, str): current = json.loads(current)
    
    if not current: current = {"balance": 0}
    
    current['balance'] = current.get('balance', 0) + amount
    kv_set(f"user:{uid}", json.dumps(current))
    
    return jsonify({"new_balance": current['balance']})
