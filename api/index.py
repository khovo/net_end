from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os
import asyncio
import requests
import json

app = Flask(__name__)
CORS(app) # Frontend እንዲገባ ይፈቅዳል

# --- CONFIG ---
TOKEN = os.environ.get('BOT_TOKEN')
KV_URL = os.environ.get('KV_REST_API_URL')
KV_TOKEN = os.environ.get('KV_REST_API_TOKEN')
FRONTEND_URL = "https://net-ui-iota.vercel.app" # ያንተ Frontend ሊንክ

# --- HELPER: Vercel KV ---
def kv_get(key):
    if not KV_URL or not KV_TOKEN: return None
    try:
        res = requests.get(f"{KV_URL}/get/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"})
        data = res.json()
        if 'result' in data and data['result']:
            return json.loads(data['result'])
    except:
        return None
    return None

def kv_set(key, value):
    if not KV_URL or not KV_TOKEN: return
    try:
        requests.post(f"{KV_URL}/set/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"}, json=value)
    except:
        pass

# --- ROUTES ---

@app.route('/')
def home():
    if not KV_URL:
        return "Backend Running, but DB NOT Connected! ❌", 200
    return "Backend Running & DB Connected! ✅", 200

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user(user_id):
    data = kv_get(f"user:{user_id}")
    if data:
        if isinstance(data, str): data = json.loads(data)
        return jsonify(data)
    
    # 🔥 AUTO-REGISTER (ሰውየው ከሌለ እንመዝግበው) 🔥
    new_user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00}
    kv_set(f"user:{user_id}", json.dumps(new_user))
    return jsonify(new_user)

@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    data = request.json
    uid = str(data.get('user_id'))
    amount = data.get('amount')
    
    current = kv_get(f"user:{uid}")
    
    # ሰውየው ከሌለ እንፍጠረው
    if not current:
        current = {"user_id": uid, "first_name": "User", "balance": 0.00}
    elif isinstance(current, str):
        current = json.loads(current)
    
    # ሂሳብ እንስራ
    current['balance'] = float(current.get('balance', 0)) + float(amount)
    
    # ሴቭ እናድርግ
    kv_set(f"user:{uid}", json.dumps(current))
    
    return jsonify({"status": "success", "new_balance": current['balance']})

# Webhook (Start Command)
@app.route('/api/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        application = ApplicationBuilder().token(TOKEN).build()
        
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            uid = str(update.effective_user.id)
            fname = update.effective_user.first_name
            
            # Save if not exists
            if not kv_get(f"user:{uid}"):
                kv_set(f"user:{uid}", json.dumps({"user_id": uid, "first_name": fname, "balance": 0.00}))
            
            btn = InlineKeyboardButton("🚀 Open App", web_app={"url": FRONTEND_URL})
            await update.message.reply_text(f"Welcome {fname}! Start here 👇", reply_markup=InlineKeyboardMarkup([[btn]]))

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
