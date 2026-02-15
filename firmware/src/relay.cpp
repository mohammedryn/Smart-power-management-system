#include "relay.h"

// LOGIC ADAPTED FOR TRANSISTOR (NPN):
// Transistor INVERTS the signal.
// So we need:
// HIGH (from ESP32) -> Transistor ON -> Pulls Relay LOW -> Relay ON.
// LOW (from ESP32)  -> Transistor OFF -> Relay Floats HIGH -> Relay OFF.

#define RELAY_ON_STATE  HIGH
#define RELAY_OFF_STATE LOW

static bool _state = false;

void relay_init() {
    pinMode(PIN_RELAY, OUTPUT);
    relay_on(); // Default ON at startup
}

void relay_on() {
    if (_state == true) return;
    digitalWrite(PIN_RELAY, RELAY_ON_STATE);
    _state = true;
    Serial.println("RELAY: ON (Active LOW)");
}

void relay_off() {
    if (_state == false) return;
    digitalWrite(PIN_RELAY, RELAY_OFF_STATE);
    _state = false;
    Serial.println("RELAY: OFF (Safe Mode)");
}

bool is_relay_on() {
    return _state;
}