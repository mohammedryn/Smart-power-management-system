# PROJECT SPECIFICATION: Smart Power Management System (Edge AI + Digital Twin)

## ROLE
You are a Senior Full-Stack IoT Engineer. Your goal is to build a robust, competition-grade prototype for a Smart Power Management System. You prioritize reliability, clean architecture, and demo-ability.

## PROJECT OVERVIEW
This system monitors electrical loads, detects faults using Machine Learning (Random Forest logic), and prevents fires via automated relay cutoffs.
### Hardware Stack
The project uses a **multi-tier distributed architecture**:

#### Tier 1: Data Acquisition (Sensor Layer)
- **STM32F401RE Nucleo:** Handles high-speed sampling (1 kHz) of current sensors.
- **Sensors:**
  - **ACS712 (30A):** Hall-effect current sensors (x4) for isolated current measurement.
  - **MLX90614:** IR Temperature sensor for monitoring wire/junction heat.
  - **MEMS Microphone:** (Built into S3-BOX-3) for voice commands.
- **Teensy 4.1 (Optional):** Mentioned for advanced/heavy analytics if needed.

#### Tier 2: Intelligence & Interface (Edge Layer)
- **ESP32-S3-BOX-3:** The main "Brain" of the system.
  - **Processor:** Dual-core Xtensa LX7 (AI acceleration).
  - **Display:** 2.4" Capacitive Touchscreen (Digital Twin UI).
  - **Connectivity:** WiFi & Bluetooth LE.
- **Actuators:**
  - **4-Channel Relay Module:** Opto-isolated 5V relays for safety limits/cutoffs.
  - **Status LEDs:** Visual feedback for system state.
  - **Speaker:** (Built into S3-BOX-3) for audio alerts/TTS.

### Software Stack
#### Firmware (Edge & Microcontrollers)
- **Frameworks:** C++ using PlatformIO / ESP-IDF.
- **OS:** FreeRTOS for real-time task scheduling.
- **AI/ML:**
  - **TensorForest / TensorFlow Lite Micro:** For on-device fault detection (Random Forest logic).
  - **Espressif ESP-SR:** For offline voice recognition (WakeNet + MultiNet).
- **UI:** LVGL (Light and Versatile Graphics Library) for the touchscreen interface.

#### Backend (Cloud/Server)
- **Language:** Python.
- **Framework:** Flask or FastAPI (for API endpoints).
- **Database:** PostgreSQL (Time-series data storage) and SQLite (Local/dev).
- **Integrations:** Twilio API (for automated SMS billing & critical alerts).

#### Frontend (User Dashboard)
- **Framework:** React.js (built with Vite).
- **Visualization:** Recharts or similar library for live power graphs.
- **Digital Twin:** Custom SVG/Canvas visualization synchronized with device state.

 
<!--
## ARCHITECTURE & FILE STRUCTURE
Enforce this folder structure strictly:
/smart-power-system
  ├── /firmware           # ESP32 Code
  │   ├── src/main.cpp
  │   └── platformio.ini
  ├── /backend            # Python Flask API
  │   ├── app.py          # Main entry
  │   ├── /models         # ML models & Logic
  │   ├── /routes         # API endpoints
  │   └── requirements.txt
  └── /frontend           # React Dashboard
      ├── src/components
      └── package.json
-->

## CODING "GOLDEN RULES" (STRICTLY FOLLOW)
1. **No Hallucinated Libraries:** Use standard libraries (Arduino.h, WiFi.h, Flask, React). Do NOT invent libraries that don't exist.
2. **Error Handling:** Every network call (WiFi, API fetch) must have a `try/catch` or error check. The system must not crash if WiFi is lost.
3. **Hardcoding:** Do NOT use `.env` files for this prototype. Put WiFi credentials and API URLs as `const` at the top of files for easy editing during the hackathon.
4. **Comments:** Comment every major function explaining *why* it exists, not just what it does.
5. **Step-by-Step Generation:** Do not generate all code at once. Wait for my trigger to start a specific module. 