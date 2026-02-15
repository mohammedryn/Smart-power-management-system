import sqlite3
import random
import time
from datetime import datetime, timedelta

DB_FILE = "power_monitor.db"

def seed_data():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # 1. Check existing Daily Summary
    c.execute("SELECT date, kwh FROM daily_summary")
    existing_days = {row[0]: row[1] for row in c.fetchall()}
    print(f"Found {len(existing_days)} existing daily entries.")

    # 2. Generate Past 7 Days
    today = datetime.now().date()
    generated_count = 0
    
    for i in range(1, 8):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        
        if day_str not in existing_days:
            # Generate realistic randomness: Weekdays higher, weekends lower? Or random.
            # Base 8kWh + random(-2, +4)
            kwh = 8.0 + random.uniform(-2.0, 4.0)
            c.execute("INSERT INTO daily_summary (date, kwh) VALUES (?, ?)", (day_str, kwh))
            generated_count += 1
            print(f"  + Added history for {day_str}: {kwh:.2f} kWh")
        else:
            print(f"  - Skipping {day_str} (Already exists: {existing_days[day_str]:.2f} kWh)")

    # 3. Handle Measurements (for the live graph)
    # If less than 10 measurements, add some history for the graph
    c.execute("SELECT COUNT(*) FROM measurements")
    count = c.fetchone()[0]
    print(f"Found {count} measurements.")
    
    if count < 10:
        print("Seeding recent measurements for graph...")
        now = time.time()
        for i in range(50):
            # Back in time 2 seconds each
            ts = now - ((50-i) * 2)
            # Create a "wave" pattern for voltage/current
            voltage = 230 + random.uniform(-2, 2)
            current = 0.5 + (0.2 * (i % 10)) # Sawtooth pattern
            power = voltage * current
            
            # Occasional spike
            if i == 45: 
                current = 2.5
                power = voltage * current
                status = "FAULT: OC"
            else:
                status = "OK"
                
            c.execute("INSERT INTO measurements (timestamp, voltage, current, power, status) VALUES (?, ?, ?, ?, ?)",
                      (ts, voltage, current, power, status))
        print("  + Added 50 measurement points.")

    conn.commit()
    conn.close()
    print(f"Seeding Complete. Added {generated_count} days of history.")

if __name__ == "__main__":
    seed_data()
