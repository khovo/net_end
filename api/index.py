from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
import json
import time

app = Flask(__name__)
CORS(app) # Frontend እንዲገባ ይፈቅዳል

# --- CONFIG ---
KV_URL = os.environ.get('KV_REST_API_URL')
KV_TOKEN = os.environ.get('KV_REST_API_TOKEN')

# --- DATABASE HELPERS ---
def db_get(key):
    try:
        res = requests.get(f"{KV_URL}/get/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"})
        data = res.json()
        if 'result' in data and data['result']:
            return json.loads(data['result'])
    except: return None
    return None

def db_set(key, value):
    try:
        requests.post(f"{KV_URL}/set/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"}, json=value)
    except: pass

# --- ROUTES ---

@app.route('/')
def home():
    return "RiyalNet Database Server is Running! 🚀", 200

# 1. USER INFO (Get or Create)
@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def handle_user(user_id):
    if request.method == 'POST':
        # Update Profile
        data = request.json
        user = db_get(f"user:{user_id}") or {"user_id": user_id, "balance": 0.00}
        user.update(data) # Merge new data
        db_set(f"user:{user_id}", json.dumps(user))
        return jsonify(user)
    else:
        # Get Profile
        user = db_get(f"user:{user_id}")
        if not user:
            # Auto-Create
            user = {"user_id": user_id, "first_name": "Guest", "balance": 0.00, "today_ads": 0}
            db_set(f"user:{user_id}", json.dumps(user))
        return jsonify(user)

# 2. ADD BALANCE (Ads or Admin)
@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    data = request.json
    uid = str(data.get('user_id'))
    amount = float(data.get('amount'))
    
    user = db_get(f"user:{uid}")
    if not user: return jsonify({"error": "User not found"}), 404
    
    user['balance'] = round(user.get('balance', 0) + amount, 2)
    # Track ads if amount is 0.50
    if amount == 0.50:
        user['today_ads'] = user.get('today_ads', 0) + 1
        
    db_set(f"user:{uid}", json.dumps(user))
    return jsonify({"status": "success", "new_balance": user['balance']})

# 3. TASKS (Admin adds, Users see)
@app.route('/api/tasks', methods=['GET', 'POST'])
def tasks():
    if request.method == 'POST':
        # Admin adding task
        new_task = request.json
        new_task['id'] = int(time.time())
        tasks = db_get("tasks") or []
        if isinstance(tasks, str): tasks = json.loads(tasks)
        tasks.append(new_task)
        db_set("tasks", json.dumps(tasks))
        return jsonify({"status": "Task Added"})
    else:
        # Get tasks
        tasks = db_get("tasks") or []
        if isinstance(tasks, str): tasks = json.loads(tasks)
        return jsonify(tasks)

# 4. WITHDRAWALS
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    uid = str(data.get('user_id'))
    amount = float(data.get('amount'))
    
    user = db_get(f"user:{uid}")
    if not user or user['balance'] < amount:
        return jsonify({"error": "Insufficient funds"}), 400
        
    # Deduct
    user['balance'] = round(user['balance'] - amount, 2)
    db_set(f"user:{uid}", json.dumps(user))
    
    # Save Request
    reqs = db_get("withdrawals") or []
    if isinstance(reqs, str): reqs = json.loads(reqs)
    
    data['status'] = 'Pending'
    data['date'] = str(time.time())
    reqs.insert(0, data) # Add to top
    db_set("withdrawals", json.dumps(reqs))
    
    return jsonify({"status": "success", "new_balance": user['balance']})

@app.route('/api/admin/withdrawals', methods=['GET'])
def get_withdrawals():
    reqs = db_get("withdrawals") or []
    if isinstance(reqs, str): reqs = json.loads(reqs)
    return jsonify(reqs)
