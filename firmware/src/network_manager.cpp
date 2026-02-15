#include "network_manager.h"
#include <WiFi.h>
#include <PubSubClient.h>
#include "secrets.h"

// --- CONFIGURATION ---
const char* ssid = WIFI_SSID;
const char* password = WIFI_PASS;

const char* mqtt_server = MQTT_SERVER;
const char* mqtt_topic_telemetry = MQTT_TOPIC_TELEMETRY;

WiFiClient espClient;
PubSubClient client(espClient);

void reconnect() {
    // Loop until we're reconnected
    // We utilize a non-blocking check pattern elsewhere, but for simplicity in reconnect
    // we try once. If this is blocking 'loop', it might freeze UI. 
    // Ideally, this should be non-blocking. 
    // For this hackathon phase, we'll do a quick check.
    
    if (!client.connected()) {
        if (WiFi.status() == WL_CONNECTED) {
            Serial.print("Attempting MQTT connection...");
            // Create a random client ID
            String clientId = "ESP32Client-";
            clientId += String(random(0xffff), HEX);
            
            if (client.connect(clientId.c_str())) {
                Serial.println("connected");
            } else {
                Serial.print("failed, rc=");
                Serial.print(client.state());
                // Don't delay here to avoid blocking UI
            }
        }
    }
}

void network_init() {
    delay(10);
    Serial.println();
    Serial.print("Connecting to ");
    Serial.println(ssid);

    WiFi.begin(ssid, password);
    // client.setServer(mqtt_server, 1883); 
    // Initial connection will happen in loop
    
    client.setServer(mqtt_server, 1883);
}

void network_loop() {
    // 1. Check WiFi
    if (WiFi.status() != WL_CONNECTED) {
        // If not connected, we rely on auto-reconnect from WiFi.begin? 
        // Or we should retry? 
        // For now, let's just assume it tries to connect background.
        // Actually, let's print status occasionally
        static unsigned long lastWiFiCheck = 0;
        if (millis() - lastWiFiCheck > 5000) {
             lastWiFiCheck = millis();
             if (WiFi.status() != WL_CONNECTED) {
                 Serial.println("WiFi not connected. Reconnecting...");
                 WiFi.reconnect();
             }
        }
        return;
    }

    // 2. Check MQTT
    if (!client.connected()) {
        static unsigned long lastMqttRetry = 0;
        if (millis() - lastMqttRetry > 5000) {
            lastMqttRetry = millis();
            reconnect();
        }
    } else {
        client.loop();
    }
}

bool network_publish(const char* topic, const char* payload) {
    if (client.connected()) {
        return client.publish(topic, payload);
    }
    return false;
}

#include <ArduinoJson.h>

void network_publish_telemetry(float voltage, float current, float power, const char* status) {
    if (!client.connected()) return;

    // Use StaticJsonDocument to avoid heap fragmentation
    StaticJsonDocument<256> doc;
    
    doc["device_id"] = "esp32_box_1";
    doc["voltage"]   = (int)voltage; // Simplify for now
    doc["current"]   = current;
    doc["power"]     = power;
    doc["status"]    = status;

    char buffer[256];
    serializeJson(doc, buffer);
    
    client.publish(mqtt_topic_telemetry, buffer);
}
