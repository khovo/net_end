from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
import json

app = Flask(__name__)
CORS(app)

# --- VERCEL KV CONFIG ---
# Vercel ላይ Storage > Connect ሲደረግ እነዚህ በራስ ሰር ይገባሉ
KV_URL = os.environ.get('KV_REST_API_URL')
KV_TOKEN = os.environ.get('KV_REST_API_TOKEN')

# --- DB HELPER FUNCTIONS ---
def db_read(key):
    if not KV_URL or not KV_TOKEN:
        print("❌ Error: Database Creds Missing")
        return None
    
    try:
        # Upstash/Vercel KV REST API: GET /get/<key>
        response = requests.get(
            f"{KV_URL}/get/{key}",
            headers={"Authorization": f"Bearer {KV_TOKEN}"}
        )
        data = response.json()
        
        # Redis returns data in 'result' field as a string
        if 'result' in data and data['result']:
            return json.loads(data['result']) # String ወደ JSON እንቀይራለን
        return None
    except Exception as e:
        print(f"❌ DB Read Error: {e}")
        return None

def db_write(key, value_dict):
    if not KV_URL or not KV_TOKEN:
        return False
    
    try:
        # Upstash/Vercel KV REST API: POST /set/<key>
        # Value must be a string
        value_str = json.dumps(value_dict)
        response = requests.post(
            f"{KV_URL}/set/{key}",
            headers={"Authorization": f"Bearer {KV_TOKEN}"},
            data=value_str
        )
        return True
    except Exception as e:
        print(f"❌ DB Write Error: {e}")
        return False

# --- ROUTES ---

@app.route('/')
def home():
    if KV_URL:
        return "✅ Backend & Vercel KV Connected!", 200
    return "❌ Database Not Connected (Check Vercel Storage Tab)", 500

@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    # 1. መረጃ ለማምጣት (GET)
    current_data = db_read(f"user:{user_id}")

    # 2. ሰውየው ከሌለ እንፍጠረው (Guest)
    if not current_data:
        current_data = {
            "user_id": user_id,
            "first_name": "Guest",
            "balance": 0.00,
            "today_ads": 0
        }
        db_write(f"user:{user_id}", current_data)

    # 3. መረጃ ለመቀየር (POST - ከ Frontend ሲመጣ)
    if request.method == 'POST':
        new_data = request.json
        # አዲሱን መረጃ ካለፈው ጋር አዋህድ (Merge)
        current_data.update(new_data)
        db_write(f"user:{user_id}", current_data)
        return jsonify({"status": "updated", "data": current_data})

    return jsonify(current_data)

@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    req = request.json
    uid = str(req.get('user_id'))
    amount = float(req.get('amount'))

    user = db_read(f"user:{uid}")
    
    if user:
        user['balance'] = round(user.get('balance', 0) + amount, 2)
        if amount == 0.50: # ማስታወቂያ ከሆነ
            user['today_ads'] = user.get('today_ads', 0) + 1
        
        db_write(f"user:{uid}", user)
        return jsonify({"status": "success", "new_balance": user['balance']})
    
    return jsonify({"error": "User not found"}), 404

# Vercel Serverless Handler
if __name__ == '__main__':
    app.run()
