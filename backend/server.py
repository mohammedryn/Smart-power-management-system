import os
import json
import time
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import paho.mqtt.client as mqtt
import google.generativeai as genai
import requests
import matplotlib
matplotlib.use('Agg') # Non-interactive backend
import matplotlib.pyplot as plt
import io
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "digikey/power/telemetry"
DATA_FILE = "energy_data.json"

# Google Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- GLOBAL STATE ---
current_data = {
    "voltage": 0,
    "current": 0,
    "power": 0,
    "status": "OFFLINE",
    "timestamp": 0
}

total_energy_kwh = 0.0
last_update_time = time.time()
COST_PER_KWH = 8.0 # INR per unit
fault_alert_sent = False # Prevent spam

import sqlite3

# --- DATABASE SETUP ---
DB_FILE = "power_monitor.db"

def init_db():
    print(f"--- DB CONFIGURATION ---")
    print(f"DB Path: {os.path.abspath(DB_FILE)}")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Measurements Table: High frequency data
    c.execute('''CREATE TABLE IF NOT EXISTS measurements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    voltage REAL,
                    current REAL,
                    power REAL,
                    status TEXT
                )''')
    # Daily Summary Table: Aggregated kWh per day
    c.execute('''CREATE TABLE IF NOT EXISTS daily_summary (
                    date TEXT PRIMARY KEY,
                    kwh REAL
                )''')
    # Logs Table: System events
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    level TEXT,
                    message TEXT
                )''')
    conn.commit()
    conn.close()

init_db()

def log_event(level, message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO logs (timestamp, level, message) VALUES (?, ?, ?)", 
              (time.time(), level, message))
    conn.commit()
    conn.close()
    print(f"[{level}] {message}")

def get_daily_kwh(date_str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT kwh FROM daily_summary WHERE date = ?", (date_str,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0.0

def update_daily_db(kwh_increment):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Upsert logic
    c.execute("INSERT INTO daily_summary (date, kwh) VALUES (?, ?) ON CONFLICT(date) DO UPDATE SET kwh = kwh + ?", 
              (today, kwh_increment, kwh_increment))
    conn.commit()
    conn.close()

def send_fault_alert(data):
    """Sends a critical alert to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing, cannot send alert.")
        return

    try:
        timestamp = datetime.fromtimestamp(data['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        caption = f"🚨 *CRITICAL SYSTEM ALERT* 🚨\n\n"
        caption += f"⚠️ **Result:** Protective Relay TRIPPED\n"
        caption += f"⏱ **Time:** {timestamp}\n\n"
        caption += f"🔍 **Fault Details:**\n"
        caption += f"• Status: `{data['status']}`\n"
        caption += f"• Voltage: `{data['voltage']} V`\n"
        caption += f"• Current: `{data['current']} A` (Limit: 0.35A)\n"
        caption += f"• Power Spike: `{data['power']} W`\n\n"
        caption += f"🛡 **Action Taken:** Circuit broken to prevent hardware damage.\n"
        caption += f"🔧 **Recommendation:** Inspect load for short circuits before manual reset."
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": caption,
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload)
        print("Telegram Fault Alert Sent!")
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

# --- MQTT CLIENT ---
def on_connect(client, userdata, flags, rc):
    log_event("INFO", f"Connected to MQTT Broker with result code {rc}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    global current_data, total_energy_kwh, last_update_time, fault_alert_sent
    try:
        payload = json.loads(msg.payload.decode())
        now = time.time()
        
        # Calculate Energy
        dt_hours = (now - last_update_time) / 3600.0
        power = float(payload.get("power", 0))
        
        if dt_hours < 0.1: # simple outlier filter
            energy_increment = (power * dt_hours) / 1000.0
            total_energy_kwh += energy_increment
            update_daily_db(energy_increment)
        
        last_update_time = now
        
        # Update Global State
        status = payload.get("status", "UNKNOWN")
        current_data = {
            "voltage": payload.get("voltage", 0),
            "current": payload.get("current", 0),
            "power": power,
            "status": status,
            "timestamp": now
        }

        # Fault Handling Logic
        if "FAULT" in status:
            log_event("WARNING", f"Fault Detected: {status} at {power:.1f}W")
            
            # Send alert only if not already sent recently (Latch)
            if not fault_alert_sent:
                send_fault_alert(current_data)
                fault_alert_sent = True
        else:
            # Reset latch if system returns to normal
            if fault_alert_sent and status == "OK":
                fault_alert_sent = False
                log_event("INFO", "System Status Normal - Fault Alert Reset")

        # Save to DB
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO measurements (timestamp, voltage, current, power, status) VALUES (?, ?, ?, ?, ?)",
                  (now, current_data["voltage"], current_data["current"], current_data["power"], current_data["status"]))
        conn.commit()
        conn.close()

        # Record for ML if active
        record_data_point(current_data)
            
    except Exception as e:
        print(f"Error parsing MQTT message: {e}")

mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def start_mqtt():
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_forever()
    except Exception as e:
        log_event("ERROR", f"MQTT Connection Failed: {e}")

mqtt_thread = threading.Thread(target=start_mqtt)
mqtt_thread.daemon = True
mqtt_thread.start()


# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

# --- DATA RECORDING (Edge AI) ---
recording_active = False
recording_label = "LEVEL_1"
DATASET_FILE = "ml_dataset.csv"

@app.route('/api/record', methods=['POST'])
def toggle_recording():
    global recording_active, recording_label
    req = request.json
    action = req.get('action') # 'start' or 'stop'
    
    if action == 'start':
        recording_label = req.get('label', 'LEVEL_1')
        recording_active = True
        return jsonify({"status": "Recording Started", "label": recording_label})
    elif action == 'stop':
        recording_active = False
        return jsonify({"status": "Recording Stopped"})
    
    return jsonify({"status": "Invalid Action"}), 400

# Helper to save data point
def record_data_point(data):
    if not recording_active: return
    
    file_exists = os.path.isfile(DATASET_FILE)
    with open(DATASET_FILE, 'a') as f:
        if not file_exists:
            f.write("voltage,current,power,label\n") # Header
        
        # Save: V, I, P, Label
        f.write(f"{data['voltage']:.2f},{data['current']:.3f},{data['power']:.2f},{recording_label}\n")

@app.route('/api/data')
def get_data():
    today = datetime.now().strftime("%Y-%m-%d")
    today_kwh = get_daily_kwh(today)
    
    # Get recent history from DB
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM measurements ORDER BY timestamp DESC LIMIT 50")
    rows = c.fetchall()
    history = [dict(row) for row in rows][::-1] # Reverse to be chronological
    
    # Get recent logs
    c.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 10")
    log_rows = c.fetchall()
    logs = [dict(row) for row in log_rows]
    
    conn.close()
    
    return jsonify({
        "live": current_data,
        "session_kwh": total_energy_kwh,
        "today_kwh": today_kwh,
        "bill": today_kwh * COST_PER_KWH,
        "history": history,
        "logs": logs,
        "recording": recording_active
    })

@app.route('/api/history')
def get_history():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT date, kwh FROM daily_summary ORDER BY date DESC LIMIT 7")
    rows = c.fetchall()
    conn.close()
    
    # Convert to dict {date: kwh}
    result = {row[0]: row[1] for row in rows}
    # Sort by date ascending for chart
    sorted_result = dict(sorted(result.items()))
    return jsonify(sorted_result)

@app.route('/api/debug/db')
def debug_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT * FROM daily_summary")
        rows = c.fetchall()
        conn.close()
        return jsonify({"count": len(rows), "rows": rows, "db_file": os.path.abspath(DB_FILE)})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/debug/reset_data')
def debug_reset_data():
    try:
        import random
        from datetime import timedelta
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # 1. Clear Tables
        c.execute("DELETE FROM daily_summary")
        c.execute("DELETE FROM measurements")
        
        # 2. Seed 7 Days
        today = datetime.now().date()
        seeded_data = []
        for i in range(0, 8):
            day = today - timedelta(days=i)
            day_str = day.strftime("%Y-%m-%d")
            # Large data: 15-22 kWh
            kwh = 15.0 + random.uniform(0.0, 7.0) 
            c.execute("INSERT INTO daily_summary (date, kwh) VALUES (?, ?)", (day_str, kwh))
            seeded_data.append({"date": day_str, "kwh": kwh})

        # 3. Seed Measurements
        now = time.time()
        for i in range(100):
            ts = now - ((100-i) * 2)
            voltage = 230 + random.uniform(-2, 2)
            current = 1.0 + (0.5 * (i % 20))
            power = voltage * current
            status = "OK"
            if i == 90: status = "FAULT: OC"
            c.execute("INSERT INTO measurements (timestamp, voltage, current, power, status) VALUES (?, ?, ?, ?, ?)",
                      (ts, voltage, current, power, status))

        conn.commit()
        
        # Verify count
        c.execute("SELECT count(*) FROM daily_summary")
        count = c.fetchone()[0]
        conn.close()
        
        return jsonify({
            "status": "Reset Complete", 
            "count": count, 
            "seeded": seeded_data 
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/analyze', methods=['POST'])
def analyze_usage():
    if not GEMINI_API_KEY:
        return jsonify({"result": "Error: GEMINI_API_KEY not set in .env"}), 500
        
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row # Enable dict access
        c = conn.cursor()
        
        # Get Weekly Data
        c.execute("SELECT date, kwh FROM daily_summary ORDER BY date DESC LIMIT 7")
        weekly_rows = c.fetchall()
        weekly_data = {row[0]: row[1] for row in weekly_rows}
        
        # Get Faults
        c.execute("SELECT * FROM logs WHERE level='WARNING' OR level='ERROR' ORDER BY timestamp DESC LIMIT 10")
        fault_rows = c.fetchall()
        recent_faults = [dict(row) for row in fault_rows if (time.time() - row[1]) < 1800] # Last 30 mins
        
        conn.close()
        
        today = datetime.now().strftime("%Y-%m-%d")
        today_val = weekly_data.get(today, 0.0)
        
        prompt = f"""
        You are an advanced home energy analyst for the "DigiKey Smart Power Monitor".
        
        **SYSTEM STATUS: {current_data['status']}**
        **FAULT HISTORY (Last 30 mins):** {len(recent_faults)} faults detected.
        
        **Data for the last 7 days (kWh):**
        {json.dumps(weekly_data, indent=2)}
        
        **Today's Usage:** {today_val:.4f} kWh
        **Current Power:** {current_data['power']} W
        
        **Analysis Request:**
        1. **System Health Check:** If status is FAULT or faults were detected, PRIORITIZE explaining why (Overcurrent > 0.35A). If normal, say "System Nominal".
        2. **Usage Trend:** Identify any unusual power surges or abnormal spikes.
        3. **Comparison:** How does today compare to the average?
        4. **Actionable Tip:** Suggest a way to save energy or improve safety.
        
        Format the output as a clean HTML snippet (use <b>, <br>, <ul>, <div class="alert"> for faults).
        Keep it professional, concise, and "Judge-Worthy".
        """
        
        model = genai.GenerativeModel('gemini-3-pro-preview')
        response = model.generate_content(prompt)
        return jsonify({"result": response.text})
        
    except Exception as e:
        return jsonify({"result": f"AI Error: {str(e)}"}), 500

# --- HELPER: Generate Chart Image ---
def generate_chart_image(data_dict):
    """Generates a dark-themed bar chart for the given data {date: kwh}."""
    dates = list(data_dict.keys())
    values = list(data_dict.values())
    
    # Setup Dark Theme
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 5))
    
    # Plot Bars
    bars = ax.bar(dates, values, color='#4facfe', edgecolor='#00f2fe')
    
    # Styling
    ax.set_title('Energy Consumption History', fontsize=16, color='white', pad=20)
    ax.set_ylabel('Energy (kWh)', fontsize=12, color='#94a3b8')
    ax.tick_params(axis='x', rotation=45, colors='#94a3b8')
    ax.tick_params(axis='y', colors='#94a3b8')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color('#334155')
    ax.spines['left'].set_color('#334155')
    
    # Add Value Labels
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.2f}',
                ha='center', va='bottom', color='white', fontsize=10)
    
    plt.tight_layout()
    
    # Save to Buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, transparent=True)
    buf.seek(0)
    plt.close(fig)
    return buf

@app.route('/api/notify', methods=['POST'])
def send_bill_telegram():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return jsonify({"result": "Error: Telegram credentials not set in .env"}), 500
        
    try:
        req_data = request.json or {}
        scope = req_data.get('scope', 'recent') # 'recent' or 'full'
        
        # 1. Select Data Range
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT date, kwh FROM daily_summary")
        rows = c.fetchall()
        conn.close()
        daily_usage = {row[0]: row[1] for row in rows}

        sorted_days = sorted(daily_usage.keys())
        if scope == 'recent':
            target_days = sorted_days[-7:]
        else:
            target_days = sorted_days # Full history
            
        data_slice = {day: daily_usage[day] for day in target_days}
        
        if not data_slice:
             return jsonify({"result": "No data available to report."})

        # 2. Generate Chart
        img_buf = generate_chart_image(data_slice)
        
        # 3. AI Analysis (Gemini)
        today = datetime.now().strftime("%Y-%m-%d")
        total_kwh = sum(data_slice.values())
        avg_kwh = total_kwh / len(data_slice) if len(data_slice) > 0 else 0
        
        ai_prompt = f"""
        Analyze this energy usage data for a smart home system:
        {json.dumps(data_slice, indent=2)}
        
        Task:
        1. Identify any **abnormal behavior** (e.g. sudden spikes, zero usage days).
        2. Compare the trend (Increasing/Decreasing?).
        3. Rate the "Energy Efficiency" (0-100%).
        4. Keep it concise (max 100 words) and formatted for a Telegram Caption (No Markdown headers like ##).
        5. Start with a bold title line like *Energy Insight*.
        """
        
        ai_text = "Analysis Unavailable"
        if GEMINI_API_KEY:
            try:
                model = genai.GenerativeModel('gemini-3-pro-preview')
                resp = model.generate_content(ai_prompt)
                ai_text = resp.text
            except Exception as e:
                ai_text = f"AI Error: {e}"

        # 4. Construct Telegram Message
        caption = f"💡 *DigiKey Smart Report* ({scope.upper()})\n\n"
        caption += f"📅 Range: {target_days[0]} to {target_days[-1]}\n"
        caption += f"⚡ Total: {total_kwh:.2f} kWh\n"
        caption += f"📊 Avg: {avg_kwh:.2f} kWh/day\n\n"
        caption += f"{ai_text}\n\n"
        caption += f"Running Status: {current_data['status']}"
        
        # 5. Send Photo
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        files = {'photo': ('chart.png', img_buf, 'image/png')}
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": caption,
            "parse_mode": "Markdown"
        }
        
        response = requests.post(url, data=data, files=files)
        
        if response.status_code == 200:
            return jsonify({"result": "Rich Report Sent Successfully!"})
        else:
            return jsonify({"result": f"Telegram Error: {response.text}"}), 500
            
    except Exception as e:
        return jsonify({"result": f"Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
