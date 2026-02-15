import sqlite3
import os

# Use ABSOLUTE PATH to verify the correct file
DB_FILE = r"d:\digikey project\backend\power_monitor.db"

def verify():
    if not os.path.exists(DB_FILE):
        print(f"ERROR: DB File not found at {DB_FILE}")
        return

    try:
        print(f"Verifying DB at: {DB_FILE}")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM daily_summary")
        count = c.fetchone()[0]
        print(f"Daily Summary Count: {count}")
        
        c.execute("SELECT date, kwh FROM daily_summary ORDER BY date DESC LIMIT 7")
        rows = c.fetchall()
        for r in rows:
            print(f"  {r[0]}: {r[1]:.2f} kWh")
            
        if count < 7:
            print("WARNING: LESS THAN 7 DAYS OF DATA FOUND!")
        else:
            print("SUCCESS: 7+ days of data confirmed.")

        conn.close()
    except Exception as e:
        print(f"ERROR READING DB: {e}")

if __name__ == "__main__":
    verify()
