from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
import json
import os
import asyncio

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# 🔥 HARDCODED KEYS (ቀጥታ የገቡ) 🔥
JSONBIN_API_KEY = "$2a$10$chn2of2sWeJyBzVyeL8rm.bTpgkDtagCcSiTrjDRnSB.hSNhkKCYC"
JSONBIN_BIN_ID = "695e0dbad0ea881f405a2247"

# ቦት ቶከን ግን ከ Vercel ይምጣ (ወይም እዚሁ መጻፍ ትችላለህ)
TOKEN = os.environ.get('BOT_TOKEN') 
FRONTEND_URL = "https://net-ui-iota.vercel.app"
ADMIN_ID = "8519835529"

# --- DB ENGINE ---
def get_db():
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
        headers = {"X-Master-Key": JSONBIN_API_KEY}
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return res.json().get("record", {})
        return {}
    except: return {}

def save_db(data):
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
        headers = {
            "X-Master-Key": JSONBIN_API_KEY,
            "Content-Type": "application/json"
        }
        requests.put(url, headers=headers, json=data)
    except: pass

# --- ROUTES ---

@app.route('/')
def home():
    # ዳታቤዙ መስራቱን ለማረጋገጥ
    db = get_db()
    status = "Connected ✅" if db else "Error ❌"
    return jsonify({"status": "Backend Live", "db_check": status})

@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    try:
        db = get_db()
        users = db.get("users", {})
        user = users.get(user_id)

        # Maintenance Check
        settings = db.get("settings", {})
        if settings.get("maintenance", False) and str(user_id) != ADMIN_ID:
            return jsonify({"error": "MAINTENANCE"}), 503

        if request.method == 'POST':
            data = request.json
            if not user: 
                user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00}
            
            user['first_name'] = data.get('first_name', user.get('first_name'))
            user['photo_url'] = data.get('photo_url', user.get('photo_url'))
            
            users[user_id] = user
            db["users"] = users
            save_db(db)
            return jsonify(user)
        
        if not user:
            user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00, "today_ads": 0}
            users[user_id] = user
            db["users"] = users
            save_db(db)
            
        return jsonify(user)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    try:
        data = request.json
        uid = str(data.get('user_id'))
        amount = float(data.get('amount'))
        
        db = get_db()
        users = db.get("users", {})
        user = users.get(uid)
        
        if not user: return jsonify({"error": "User not found"}), 404
        
        user['balance'] = round(user.get('balance', 0) + amount, 2)
        if amount == 0.50:
            user['today_ads'] = user.get('today_ads', 0) + 1
            
        users[uid] = user
        db["users"] = users
        save_db(db)
        
        return jsonify({"status": "success", "new_balance": user['balance']})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- ADMIN ROUTES ---
@app.route('/api/admin/action', methods=['POST'])
def admin_action():
    try:
        req = request.json
        if str(req.get('admin_id')) != ADMIN_ID:
            return jsonify({"error": "Unauthorized"}), 403
            
        action = req.get('action')
        db = get_db()
        
        if action == "add_task":
            tasks = db.get("global_tasks", [])
            new_task = req.get('task')
            new_task['id'] = int(time.time())
            tasks.append(new_task)
            db["global_tasks"] = tasks
            save_db(db)
            return jsonify({"status": "Task Added"})
            
        return jsonify({"status": "Action Complete"})
    except: return jsonify({"error": "Failed"}), 500

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    db = get_db()
    return jsonify(db.get("global_tasks", []))

# --- WEBHOOK ---
@app.route('/api/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        if not TOKEN: return "No Token", 200
        
        try:
            application = ApplicationBuilder().token(TOKEN).build()
            async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
                u = update.effective_user
                btn = InlineKeyboardButton("🚀 Open App", web_app={"url": FRONTEND_URL})
                await update.message.reply_text(f"Hello {u.first_name}!", reply_markup=InlineKeyboardMarkup([[btn]]))

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
        except: return "Error"
        return "OK"
    return "Error"
