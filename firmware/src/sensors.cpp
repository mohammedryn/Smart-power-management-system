#include "sensors.h"
#include "ui.h"
#include "relay.h"
#include <Arduino.h>
#include <EloquentTinyML.h>
#include "model_data.h"
#include "class_map.h"

// 3 inputs, 4 outputs (FAULT, IDLE, L1, L2), 2kb arena
Eloquent::TinyML::TfLite<3, 4, 2048> ml; 

// --- GLOBALS ---
volatile float g_voltage = 0.0;
volatile float g_current = 0.0;
volatile float g_power = 0.0;
volatile bool g_fault_state = false; 
char g_status[32] = "IDLE";
int last_class_idx = -1;

// --- CALIBRATION ---
float CAL_VOLTAGE = 533.6; 
float CAL_CURRENT = 11.0; 

int ZERO_VOLT = 2048; 
int ZERO_AMP = 2048; 

// FORWARD DECLARATION
void sensor_task(void *pvParameters);

void check_serial_commands() {
    if (Serial.available()) {
        String cmd = Serial.readStringUntil('\n');
        cmd.trim();
        if (cmd.startsWith("VCAL:")) {
            CAL_VOLTAGE = cmd.substring(5).toFloat();
            Serial.print("UPDATED V_CAL: "); Serial.println(CAL_VOLTAGE);
        }
        else if (cmd.startsWith("ICAL:")) {
            CAL_CURRENT = cmd.substring(5).toFloat();
            Serial.print("UPDATED I_CAL: "); Serial.println(CAL_CURRENT);
        }
        else if (cmd.equalsIgnoreCase("RELAY:ON")) {
            relay_on();
            Serial.println("Force Relay ON");
        }
        else if (cmd.equalsIgnoreCase("RELAY:OFF")) {
            relay_off();
            Serial.println("Force Relay OFF");
        }
        else if (cmd.equalsIgnoreCase("RESET")) {
            g_fault_state = false;
            relay_on();
            Serial.println("FAULT CLEARED. RELAY ON.");
        }
    }
}

float get_rms_voltage(int samples) {
    unsigned long sum_sq = 0;
    for (int i=0; i<samples; i++) {
        int raw = analogRead(PIN_VOLTAGE);
        int diff = raw - ZERO_VOLT; 
        sum_sq += (unsigned long)(diff * diff);
        delayMicroseconds(50); 
    }
    float rms_adc = sqrt((float)sum_sq / samples);
    float final_volts = rms_adc * (3.3 / 4095.0) * CAL_VOLTAGE; 
    if (final_volts < 15.0) return 0.0;
    return final_volts; 
}

float get_rms_current(int samples, int* wave_out) {
    double sum_sq = 0; 
    int chart_index = 0;

    // Trigger Logic
    unsigned long timeout = millis() + 20;
    while(millis() < timeout) {
        if (analogRead(PIN_CURRENT) < ZERO_AMP) {
            while(millis() < timeout && analogRead(PIN_CURRENT) < ZERO_AMP);
            break; 
        }
    }
    
    for (int i=0; i<samples; i++) {
        int raw = analogRead(PIN_CURRENT);
        int diff = raw - ZERO_AMP; 
        sum_sq += (double)(diff * diff); 
        
        if (wave_out != NULL && (i % 20 == 0) && chart_index < 50) {
            wave_out[chart_index] = raw;
            chart_index++;
        }
        
        delayMicroseconds(50);
    }
    float rms_adc = sqrt((float)(sum_sq / samples));
    return rms_adc * (3.3 / 4095.0) * CAL_CURRENT;
}

void sensors_init() {
    pinMode(PIN_VOLTAGE, INPUT);
    pinMode(PIN_CURRENT, INPUT);
    delay(100);

    long v_sum = 0, c_sum = 0;
    for(int i=0; i<1000; i++) {
        v_sum += analogRead(PIN_VOLTAGE);
        c_sum += analogRead(PIN_CURRENT);
        delayMicroseconds(50);
    }
    ZERO_VOLT = v_sum / 1000;
    ZERO_AMP = c_sum / 1000;
    
    // Init ML
    ml.begin(model_data);
    Serial.println("AI SYSTEM ONLINE: TFLite Initialized.");
    strcpy(g_status, "AI INIT");
    ui_update_status(g_status);
    
    xTaskCreatePinnedToCore(sensor_task, "Sens", 8192, NULL, 1, NULL, 0); 
}

void sensor_task(void *pvParameters) {
    while (1) {
        check_serial_commands();

        int waveform[50];
        float v_rms = get_rms_voltage(1000);
        float i_rms = get_rms_current(1000, waveform); 

        // Noise Gate
        if (v_rms < 5.0) v_rms = 0.0;
        if (i_rms < 0.10) i_rms = 0.0; 

        float power_va = v_rms * i_rms;

        g_voltage = v_rms;
        g_current = i_rms;
        g_power = power_va;

        Serial.print(millis()); Serial.print(",");
        Serial.print(v_rms, 1); Serial.print(",");
        Serial.print(i_rms, 3); Serial.print(",");
        Serial.println(power_va, 1);

        ui_update_val_1(g_power);
        ui_update_val_2(g_current);
        ui_update_val_3(g_voltage);
        ui_update_status(g_status); // Update Status on Screen
        ui_update_chart(waveform, 50); 
        
        if (g_fault_state) {
            strcpy(g_status, "FAULT: OC");
            relay_off();
        }
        else {
            // --- AI INFERENCE ---
            float input[3] = { v_rms, i_rms, power_va };
            float proba[4] = {0}; 
            ml.predict(input, proba); 
            
            // Find ArgMax
            int class_idx = 0;
            float max_prob = proba[0];
            for(int i=1; i<4; i++) {
                if(proba[i] > max_prob) {
                    class_idx = i;
                    max_prob = proba[i];
                }
            }
            
            if (class_idx >= 0 && class_idx < 4) {
                 strncpy(g_status, CLASS_NAMES[class_idx], 31);
                 
                 // Debug Print only on change to avoid flooding
                 if (class_idx != last_class_idx) {
                     Serial.print("AI PREDICTION CHANGE: "); 
                     Serial.println(CLASS_NAMES[class_idx]); 
                     last_class_idx = class_idx;
                 }
            }
            
            // CLASS 0 IS FAULT
            if (class_idx == 0 || i_rms > 0.35) { 
                 g_fault_state = true;
                 strcpy(g_status, "AI FAULT");
                 relay_off();
                 Serial.println("!!! AI DETECTED FAULT -> RELAY OFF !!!");
            } else {
                 relay_on();
            }
        }

        vTaskDelay(pdMS_TO_TICKS(100)); 
    }
}