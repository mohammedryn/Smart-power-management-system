import sqlite3
import random
import time
import os
from datetime import datetime, timedelta

# Use ABSOLUTE PATH to ensure we hit the right DB
DB_FILE = r"d:\digikey project\backend\power_monitor.db"

def force_seed():
    print(f"Connecting to absolute path: {DB_FILE}")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # 1. FORCE CLEAR TABLES
    print("Clearing existing data...")
    c.execute("DELETE FROM daily_summary")
    c.execute("DELETE FROM measurements")
    c.execute("DELETE FROM logs")
    conn.commit()

    # 2. Generate Past 7 Days (Very Large Data)
    today = datetime.now().date()
    
    print("Generating 7 days of LARGE history...")
    for i in range(0, 8): # 0 to 7 days back
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        
        # Base 15kWh + random(-2, +5) -> Range 13-20 kWh per day
        # This is "large" compared to 0.006
        kwh = 15.0 + random.uniform(-2.0, 5.0)
        c.execute("INSERT INTO daily_summary (date, kwh) VALUES (?, ?)", (day_str, kwh))
        print(f"  + Added history for {day_str}: {kwh:.2f} kWh")

    # 3. Generate Measurements (Recent 1 hour)
    print("Generating recent measurements...")
    now = time.time()
    for i in range(100): # 100 points
        ts = now - ((100-i) * 2)
        # Create a "wave" pattern for voltage/current
        voltage = 230 + random.uniform(-2, 2)
        current = 1.5 + (0.5 * (i % 20)) # Higher base current
        power = voltage * current
        
        status = "OK"
        if i == 95: 
            status = "FAULT: OC"
            
        c.execute("INSERT INTO measurements (timestamp, voltage, current, power, status) VALUES (?, ?, ?, ?, ?)",
                  (ts, voltage, current, power, status))

    conn.commit()
    conn.close()
    print("FORCE SEED COMPLETE. Database reset with LARGE dummy data.")

if __name__ == "__main__":
    force_seed()
