from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os
import requests
import json
import asyncio

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
# Vercel Environment Variables ላይ BOT_TOKEN ማስገባትህን እንዳትረሳ!
TOKEN = os.environ.get('BOT_TOKEN')
KV_URL = os.environ.get('KV_REST_API_URL')
KV_TOKEN = os.environ.get('KV_REST_API_TOKEN')

# ያንተ የ Frontend (Mini App) ሊንክ
FRONTEND_URL = "https://net-ui-iota.vercel.app"

# --- DATABASE HELPER FUNCTIONS ---
def db_read(key):
    if not KV_URL or not KV_TOKEN: return None
    try:
        res = requests.get(f"{KV_URL}/get/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"})
        data = res.json()
        if 'result' in data and data['result']:
            return json.loads(data['result'])
    except: return None
    return None

def db_write(key, value):
    if not KV_URL or not KV_TOKEN: return
    try:
        requests.post(f"{KV_URL}/set/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"}, json=value)
    except: pass

# --- TELEGRAM BOT LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    first_name = user.first_name
    
    # 1. ተጠቃሚውን መዝግብ (ዳታቤዝ ላይ ከሌለ)
    current_user = db_read(f"user:{uid}")
    if not current_user:
        new_user = {
            "user_id": uid,
            "first_name": first_name,
            "balance": 0.00,
            "today_ads": 0,
            "total_ref": 0 # ለ Invite System
        }
        db_write(f"user:{uid}", json.dumps(new_user))
        
        # የጋበዘውን ሰው (Referrer) መዝግብ (start payload ካለ)
        args = context.args
        if args and args[0] != uid:
            referrer_id = args[0]
            referrer = db_read(f"user:{referrer_id}")
            if referrer:
                referrer['balance'] = round(referrer.get('balance', 0) + 1.00, 2) # 1 ብር ቦነስ
                referrer['total_ref'] = referrer.get('total_ref', 0) + 1
                db_write(f"user:{referrer_id}", json.dumps(referrer))
                # ለጋበዘው ሰው መልእክት እንላክ (Optional)
                try:
                    await context.bot.send_message(chat_id=referrer_id, text=f"🎉 You invited {first_name}! +1.00 ETB")
                except: pass

    # 2. የመልስ መልእክት (ከ Mini App Button ጋር)
    keyboard = [
        [InlineKeyboardButton("🚀 Start Earning (አፑን ክፈት)", web_app=WebAppInfo(url=FRONTEND_URL))],
        [InlineKeyboardButton("📢 Join Channel", url="https://t.me/your_channel_link")] # ያንተን ቻናል አስገባ
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"ሰላም {first_name}! 👋\n\nወደ RiyalNet እንኳን በደህና መጡ።\nማስታወቂያ በማየት እና ጓደኞችን በመጋበዝ ገንዘብ ይስሩ። 👇",
        reply_markup=reply_markup
    )

# --- WEBHOOK ROUTE (ቴሌግራም የሚጠራው) ---
@app.route('/api/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        # Bot Application ማዘጋጀት
        application = ApplicationBuilder().token(TOKEN).build()
        application.add_handler(CommandHandler("start", start))

        async def main():
            await application.initialize()
            try:
                update = Update.de_json(request.get_json(force=True), application.bot)
                await application.process_update(update)
            except Exception as e:
                print(f"Error: {e}")
            finally:
                await application.shutdown()

        # Run Async Loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        loop.run_until_complete(main())
        return "OK"
    return "Error"

# --- API ROUTES (ለ FRONTEND) ---

@app.route('/')
def home():
    if KV_URL: return "Backend & Database Connected! 🚀 (Bot Ready)", 200
    return "Backend Running but DB Disconnected ❌", 200

@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    # Get User
    user = db_read(f"user:{user_id}")
    
    # Update from Frontend (e.g. Photo)
    if request.method == 'POST':
        data = request.json
        if not user: user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00}
        user.update(data)
        db_write(f"user:{user_id}", json.dumps(user))
        return jsonify(user)
    
    if not user:
        # Auto-create if not found
        user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00}
        db_write(f"user:{user_id}", json.dumps(user))
        
    return jsonify(user)

@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    data = request.json
    uid = str(data.get('user_id'))
    amount = float(data.get('amount'))
    
    user = db_read(f"user:{uid}")
    if user:
        user['balance'] = round(user.get('balance', 0) + amount, 2)
        if amount == 0.50: # Ad Reward
            user['today_ads'] = user.get('today_ads', 0) + 1
        
        db_write(f"user:{uid}", json.dumps(user))
        return jsonify({"status": "success", "new_balance": user['balance']})
    
    return jsonify({"error": "User not found"}), 404

# Vercel Serverless Handler
if __name__ == '__main__':
    app.run()
