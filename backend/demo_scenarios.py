import time
import json
import random
import paho.mqtt.client as mqtt

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "gridguard/power/telemetry"

client = mqtt.Client()
connected = False

def on_connect(client, userdata, flags, rc):
    global connected
    if rc == 0:
        print("Connected to MQTT Broker!")
        connected = True
    else:
        print(f"Failed to connect, return code {rc}")

client.on_connect = on_connect
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

# Wait for connection
while not connected:
    time.sleep(0.1)

def send_data(voltage, current, status="OK"):
    power = voltage * current
    payload = {
        "voltage": round(voltage, 1),
        "current": round(current, 3),
        "power": round(power, 2),
        "status": status
    }
    client.publish(MQTT_TOPIC, json.dumps(payload))
    print(f"Sent: {payload}")

def scenario_normal():
    print("\n--- SIMULATING NORMAL OPERATION ---")
    try:
        while True:
            v = 230 + random.uniform(-2, 2)
            c = 0.15 + random.uniform(0.01, 0.05) # Safe range
            send_data(v, c, "OK")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping scenario.")

def scenario_overload():
    print("\n--- SIMULATING OVERLOAD FAULT ---")
    current = 0.20
    try:
        while True:
            current += 0.02 # Ramp up
            v = 230 + random.uniform(-2, 2)
            
            status = "OK"
            if current > 0.35:
                status = "FAULT: OC"
                print("!!! TRIGGERING FAULT !!!")
            
            send_data(v, current, status)
            
            if current > 0.50:
                current = 0.20 # Reset loop
                print("Resetting loop...")
                time.sleep(2)
                
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping scenario.")

def scenario_spike():
    print("\n--- SIMULATING POWER SPIKE ---")
    # Send normal data first
    for _ in range(3):
        send_data(230, 0.15, "OK")
        time.sleep(1)
        
    # HUGE SPIKE
    print(">>> SPIKE <<<")
    send_data(240, 2.5, "FAULT: COMPONENT SHORT")
    time.sleep(0.5)
    
    # Back to zero (protection tripped)
    print(">>> CUTOFF <<<")
    send_data(0, 0, "OFFLINE")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=["normal", "overload", "spike"], default="normal")
    args = parser.parse_args()

    if args.scenario == "normal":
        scenario_normal()
    elif args.scenario == "overload":
        scenario_overload()
    elif args.scenario == "spike":
        scenario_spike()

    client.loop_stop()
    client.disconnect()
