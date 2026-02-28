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
MQTT_TOPIC = "gridguard/power/telemetry"
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
COST_PER_KWH = 2.0 # INR per unit
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
    # Automatically mark device as offline if no updates received in 5 seconds
    if time.time() - last_update_time > 5.0:
        current_data["status"] = "OFFLINE"
        current_data["voltage"] = 0
        current_data["current"] = 0
        current_data["power"] = 0

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
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Get Weekly Data
        c.execute("SELECT date, kwh FROM daily_summary ORDER BY date DESC LIMIT 7")
        weekly_rows = c.fetchall()
        weekly_data = {row[0]: row[1] for row in weekly_rows}
        
        # Get ALL fault + warning logs
        c.execute("SELECT * FROM logs WHERE level='WARNING' OR level='ERROR' ORDER BY timestamp DESC LIMIT 50")
        fault_rows = c.fetchall()
        all_faults = [dict(row) for row in fault_rows]
        recent_faults = [f for f in all_faults if (time.time() - f['timestamp']) < 1800]
        
        # Get all info logs
        c.execute("SELECT * FROM logs WHERE level='INFO' ORDER BY timestamp DESC LIMIT 20")
        info_logs = [dict(row) for row in c.fetchall()]
        
        # Get last 100 measurements for full statistical analysis
        c.execute("SELECT timestamp, voltage, current, power, status FROM measurements ORDER BY timestamp DESC LIMIT 100")
        measurements = [dict(row) for row in c.fetchall()]
        
        conn.close()
        
        today = datetime.now().strftime("%Y-%m-%d")
        today_val = weekly_data.get(today, 0.0)
        
        # Pre-compute stats for richer context
        if measurements:
            voltages = [m['voltage'] for m in measurements]
            currents = [m['current'] for m in measurements]
            powers = [m['power'] for m in measurements]
            avg_voltage = sum(voltages) / len(voltages)
            avg_current = sum(currents) / len(currents)
            avg_power = sum(powers) / len(powers)
            peak_power = max(powers)
            min_power = min(powers)
            fault_count_in_measurements = sum(1 for m in measurements if 'FAULT' in m.get('status', ''))
        else:
            avg_voltage = avg_current = avg_power = peak_power = min_power = 0
            fault_count_in_measurements = 0
        
        weekly_values = list(weekly_data.values())
        weekly_avg = sum(weekly_values) / len(weekly_values) if weekly_values else 0
        weekly_peak = max(weekly_values) if weekly_values else 0
        weekly_min = min(weekly_values) if weekly_values else 0
        projected_monthly_bill = weekly_avg * 30 * COST_PER_KWH
        
        prompt = f"""
        You are a WORLD-CLASS power systems engineer and energy data scientist providing a comprehensive, professional-grade deep-dive analysis report for the "GridGuard Smart Power Management System". This report must be exhaustive, precise, and actionable. Leave absolutely nothing out.

        =============================================
        LIVE SYSTEM SNAPSHOT
        =============================================
        - Current Status: {current_data['status']}
        - Live Voltage (RMS): {current_data['voltage']:.2f} V
        - Live Current (RMS): {current_data['current']:.3f} A
        - Live Power: {current_data['power']:.2f} W
        - Today's Total Energy: {today_val:.4f} kWh
        - Today's Cost: Rs.{today_val * COST_PER_KWH:.2f} (at Rs.{COST_PER_KWH}/kWh)

        =============================================
        STATISTICAL ANALYSIS (Last 100 Measurements)
        =============================================
        - Average Voltage: {avg_voltage:.2f} V
        - Average Current: {avg_current:.3f} A
        - Average Power Draw: {avg_power:.2f} W
        - Peak Power Recorded: {peak_power:.2f} W
        - Minimum Power Recorded: {min_power:.2f} W
        - Fault Events in Sample: {fault_count_in_measurements} out of {len(measurements)} readings

        =============================================
        7-DAY ENERGY HISTORY (kWh per day)
        =============================================
        {json.dumps(weekly_data, indent=2)}

        - 7-Day Average: {weekly_avg:.3f} kWh/day
        - 7-Day Peak Day: {weekly_peak:.3f} kWh
        - 7-Day Minimum Day: {weekly_min:.3f} kWh
        - Projected Monthly Bill: Rs.{projected_monthly_bill:.2f}

        =============================================
        FAULT & WARNING LOG (All Time, Last 50)
        =============================================
        Total Faults/Warnings on Record: {len(all_faults)}
        Faults in Last 30 Minutes: {len(recent_faults)}
        Fault Log Details: {json.dumps(all_faults[:20], indent=2)}

        =============================================
        SYSTEM EVENTS LOG (INFO)
        =============================================
        {json.dumps(info_logs, indent=2)}

        =============================================
        FULL ANALYSIS REQUEST - MANDATORY SECTIONS
        =============================================

        Generate a FULL, DEEPLY DETAILED HTML report covering ALL of the following sections. Do not skip any section. Use rich formatting: headings with <h3 style="color:#00f2fe; margin-top:20px;">, sections with <div style="margin-bottom: 20px;">, key values in <b style="color:#4facfe">, lists with <ul style="padding-left: 20px;"><li>, and highlight faults with <span style="color:#ef4444">. 
        
        CRITICAL UI RULES: Your entire output will be injected into a dark-themed glassmorphism UI. NEVER use styling like `background: white` or `color: black` or generic `style="background-color: #ffffff;"` on any element. Do not wrap the report in a body or html tag. Just output the raw styled HTML sections.

        **SECTION 1: EXECUTIVE SUMMARY**
        Provide a 3-4 sentence high-level verdict on the system's overall health, energy efficiency, and financial standing.

        **SECTION 2: LIVE POWER STATE ANALYSIS**
        Deeply analyze the current live readings. Is the voltage within acceptable Indian mains range (220-240V)? Is the current safe (below 0.35A trip threshold)? What does the power draw suggest about what appliance is likely connected? Are there any anomalies visible?

        **SECTION 3: FAULT & SAFETY INCIDENT ANALYSIS**
        Provide a detailed post-mortem on every fault/warning event in the log. For EACH fault: what was the probable cause, when did it occur (human-readable timestamp), how severe was it, did the relay trip correctly? If there are zero faults, explain why the system is operating safely.

        **SECTION 4: ENERGY CONSUMPTION DEEP DIVE (7-Day Trend)**
        Analyze day-over-day trend (increasing/decreasing?). Identify the highest and lowest consumption days and speculate on the cause. Calculate the percentage deviation from the weekly average for each day. What does the consumption curve suggest about usage patterns (peak hours, weekday vs weekend)?

        **SECTION 5: VOLTAGE & CURRENT STABILITY REPORT**
        Based on the 100-measurement statistics: Is the voltage stable? Any significant sag or swell? Is the current profile smooth or erratic? Is the system under-loaded or running near capacity? Comment on the consistency of readings.

        **SECTION 6: FINANCIAL & BILLING ANALYSIS**
        Provide a complete cost breakdown: Today's bill, projected weekly bill, projected monthly bill, projected annual bill (all in INR at Rs.{COST_PER_KWH}/kWh). Compare today's spend vs the 7-day average. State the carbon footprint implication (India grid avg: 0.82 kg CO2 per kWh).

        **SECTION 7: PREDICTIVE RISK ASSESSMENT**
        Based on all data: What is the risk level (LOW/MEDIUM/HIGH) of a fault occurring in the next 24 hours? Justify using the data. Are there patterns that suggest the relay may trip again? What preventive actions should be taken immediately?

        **SECTION 8: ACTIONABLE RECOMMENDATIONS**
        Provide at least 5 specific, highly actionable recommendations to reduce energy consumption, improve safety, optimize costs, and maintain system health. Each recommendation must reference the actual data values above.

        **SECTION 9: SYSTEM HEALTH SCORECARD**
        Rate the system on a 0-100 scale for: Safety, Energy Efficiency, Voltage Stability, Cost Optimization, and Overall Health. Display as an HTML table (<table style="width:100%;border-collapse:collapse;">) with scores and a brief one-line justification for each.

        This is a hackathon submission report. Make it world-class. Be thorough, precise, and technically impressive.
        """
        
        model = genai.GenerativeModel('gemini-3-pro-preview')
        response = model.generate_content(prompt)
        # Strip markdown code fences if Gemini wraps output in ```html ... ```
        result_text = response.text.strip()
        if result_text.startswith('```'):
            result_text = result_text.split('\n', 1)[-1]  # Remove first line (```html)
            result_text = result_text.rsplit('```', 1)[0]  # Remove trailing ```
        return jsonify({"result": result_text})
        
    except Exception as e:
        return jsonify({"result": f"AI Error: {str(e)}"}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    if not GEMINI_API_KEY:
        return jsonify({"result": "Error: GEMINI_API_KEY not set in .env"}), 500
        
    try:
        req_data = request.json or {}
        user_message = req_data.get('message', '')
        
        if not user_message:
            return jsonify({"result": "Error: No message provided"}), 400
            
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Gathering Context
        # 1. Weekly Data
        c.execute("SELECT date, kwh FROM daily_summary ORDER BY date DESC LIMIT 7")
        weekly_data = {row[0]: row[1] for row in c.fetchall()}
        
        # 2. Recent Events/Faults (last 2 hours)
        two_hours_ago = time.time() - 7200
        c.execute("SELECT * FROM logs WHERE timestamp > ? ORDER BY timestamp DESC LIMIT 20", (two_hours_ago,))
        recent_logs = [dict(row) for row in c.fetchall()]
        
        # 3. Latest Measurements
        c.execute("SELECT timestamp, voltage, current, power, status FROM measurements ORDER BY timestamp DESC LIMIT 10")
        recent_measurements = [dict(row) for row in c.fetchall()]
        
        conn.close()
        
        today = datetime.now().strftime("%Y-%m-%d")
        today_val = weekly_data.get(today, 0.0)
        
        # Construct the Prompt
        prompt = f"""
        You are a professional energy data analyst for the "GridGuard Smart Power Monitor" IoT system. You have direct access to the system's live sensor telemetry and its historical database. You are NOT a chatbot — you are a specialist who interprets measurements and gives sharp, data-driven, structured responses.

        Your tone: Confident, professional, and precise. Explain things like a senior electrical engineer talking to a non-technical homeowner. Use relevant emojis where helpful. Always back your answers with specific numbers from the data below.

        === LIVE SENSOR TELEMETRY ===
        System Status: {current_data['status']}
        Measured Voltage (RMS): {current_data['voltage']:.2f} V
        Measured Current (RMS): {current_data['current']:.3f} A
        Measured Real Power: {current_data['power']:.2f} W
        Today's Total Energy (from DB): {today_val:.4f} kWh

        === 7-DAY ENERGY DATABASE (kWh/day) ===
        {json.dumps(weekly_data, indent=2)}

        === RECENT SYSTEM EVENT LOGS (Last 2 hours) ===
        {json.dumps(recent_logs, indent=2)}

        === LAST 10 SENSOR READINGS ===
        {json.dumps(recent_measurements, indent=2)}

        === USER'S QUESTION ===
        {user_message}

        === STRICT RESPONSE RULES ===
        1. Answer ONLY using the sensor telemetry, database records above, and your own real-world electrical/energy expertise.
        2. NEVER reference the dashboard code, how the app is built, configuration constants, or "what the system is set to". You have no knowledge of source code or software constants. You only see measurements and database records.
        3. For questions about electricity rates in India: use your real-world knowledge of DISCOM tariffs, slab structures, and state averages. Do NOT invent a single rate — explain the slab-based reality (e.g. MSEDCL, BESCOM, TNEB rates).
        4. For cost/billing questions: use the kWh values from the DB. Apply the standard Tier-2 residential rate (Rs. 6-8/kWh) for realistic estimates. Always show the calculation step by step.
        5. For fault/safety questions: quote the exact log entries. State the exact measured current and voltage that triggered the fault.
        6. For trend analysis: compute exact % changes day-over-day. Identify peak and trough days by name with values.
        7. If the system is OFFLINE (all live readings = 0), acknowledge it plainly, then shift focus to the historical data.
        8. Format: Use **bold** for every key number/value. Use bullet points (- ) for lists. Use ### for section headings in multi-part answers.
        9. Use Markdown ONLY. Never use HTML tags.
        10. Write like a brief analyst report — structured, precise, and actionable. Never give a lazy one-liner for a real question.
        """
        
        # Use gemini-3-pro-preview for consistency with other working endpoints
        model = genai.GenerativeModel('gemini-3-pro-preview')
        response = model.generate_content(prompt)
        
        return jsonify({"result": response.text})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
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
                # Deep analysis context
                conn2 = sqlite3.connect(DB_FILE)
                conn2.row_factory = sqlite3.Row
                c2 = conn2.cursor()
                c2.execute("SELECT * FROM logs WHERE level='WARNING' OR level='ERROR' ORDER BY timestamp DESC LIMIT 50")
                all_faults = [dict(row) for row in c2.fetchall()]
                c2.execute("SELECT timestamp, voltage, current, power, status FROM measurements ORDER BY timestamp DESC LIMIT 100")
                measurements = [dict(row) for row in c2.fetchall()]
                conn2.close()

                today_val_tg = data_slice.get(today, 0.0)
                if measurements:
                    voltages = [m['voltage'] for m in measurements]
                    currents = [m['current'] for m in measurements]
                    powers = [m['power'] for m in measurements]
                    avg_voltage = sum(voltages) / len(voltages)
                    avg_current = sum(currents) / len(currents)
                    avg_power = sum(powers) / len(powers)
                    peak_power = max(powers)
                    fault_count = sum(1 for m in measurements if 'FAULT' in m.get('status',''))
                else:
                    avg_voltage = avg_current = avg_power = peak_power = fault_count = 0

                projected_monthly = avg_kwh * 30 * COST_PER_KWH

                ai_prompt = f"""
                You are a world-class power systems engineer writing a comprehensive deep-dive energy report for the GridGuard Smart Power Monitor. This will be sent as a Telegram message so use plain text with emojis for structure (NO HTML, NO Markdown headers with #).

                === LIVE DATA ===
                Status: {current_data['status']}
                Live Power: {current_data['power']:.2f} W | Voltage: {current_data['voltage']:.2f} V | Current: {current_data['current']:.3f} A
                Today's Usage: {today_val_tg:.4f} kWh | Today's Cost: Rs.{today_val_tg * COST_PER_KWH:.2f}

                === STATISTICS (Last 100 Readings) ===
                Avg Voltage: {avg_voltage:.2f}V | Avg Current: {avg_current:.3f}A | Avg Power: {avg_power:.2f}W
                Peak Power: {peak_power:.2f}W | Fault Events: {fault_count}/{len(measurements)}

                === 7-DAY ENERGY DATA ===
                {json.dumps(data_slice, indent=2)}
                Total: {total_kwh:.2f} kWh | Daily Avg: {avg_kwh:.2f} kWh | Projected Monthly Bill: Rs.{projected_monthly:.2f}

                === FAULTS (Last 20) ===
                {json.dumps(all_faults[:20])}

                Write a FULL deep-dive report with these sections (use emojis as section headers, keep it readable for Telegram):
                1. ⚡ EXECUTIVE SUMMARY
                2. 🔌 LIVE POWER STATE
                3. ⚠️ FAULT & SAFETY ANALYSIS
                4. 📈 7-DAY ENERGY TREND
                5. 💰 FINANCIAL BREAKDOWN (daily/weekly/monthly/annual + carbon footprint in kg CO2)
                6. 🎯 RISK ASSESSMENT (LOW/MEDIUM/HIGH for next 24hrs with justification)
                7. ✅ TOP 5 RECOMMENDATIONS
                8. 🏆 HEALTH SCORECARD (Safety / Efficiency / Stability / Cost — rated X/100)

                Be thorough, data-driven, and technically precise. Reference actual values.
                """

                model = genai.GenerativeModel('gemini-3-pro-preview')
                resp = model.generate_content(ai_prompt)
                ai_text = resp.text
            except Exception as e:
                ai_text = f"AI Error: {e}"

        # 4. Construct Short Caption for Photo
        caption = f"💡 *GridGuard Smart Report* ({scope.upper()})\n\n"
        caption += f"📅 Range: {target_days[0]} to {target_days[-1]}\n"
        caption += f"⚡ Total: {total_kwh:.2f} kWh\n"
        caption += f"📊 Avg: {avg_kwh:.2f} kWh/day\n"
        
        # 5. Send Photo with Short Caption
        photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        files = {'photo': ('chart.png', img_buf, 'image/png')}
        photo_data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": caption,
            "parse_mode": "Markdown"
        }
        
        photo_resp = requests.post(photo_url, data=photo_data, files=files)
        
        if photo_resp.status_code != 200:
            return jsonify({"result": f"Telegram Photo Error: {photo_resp.text}"}), 500

        # 6. Send the Full AI Deep Analysis as a Text Message
        ai_msg = f"{ai_text}\n\nRunning Status: {current_data['status']}"
        
        # Protect against the 4096 character limit for text messages
        if len(ai_msg) > 4000:
            ai_msg = ai_msg[:4000] + "\n...(truncated)"
            
        text_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        text_data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": ai_msg
            # Telegram sometimes trips on AI-generated raw markdown if it has unclosed tags, so we send plain text output
        }
        
        text_resp = requests.post(text_url, json=text_data)
        
        if text_resp.status_code == 200:
            return jsonify({"result": "Rich Report & Analysis Sent Successfully!"})
        else:
            return jsonify({"result": f"Telegram Text Error: {text_resp.text}"}), 500
            
    except Exception as e:
        return jsonify({"result": f"Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
