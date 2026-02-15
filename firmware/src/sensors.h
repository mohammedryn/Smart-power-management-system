#ifndef SENSORS_H
#define SENSORS_H

#include <Arduino.h>

// PIN DEFINITIONS
#define PIN_VOLTAGE 10 // ADC1_CH9 (Available on header)
#define PIN_CURRENT 9  // ADC1_CH8 (Available on header)

// Global Shared Variables (Read by UI, Written by Sensor Task)
extern volatile float g_voltage;
extern volatile float g_current;
extern volatile float g_power;
extern char g_status[32];

// Initialization
void sensors_init();

// The FreeRTOS Task function
void sensor_task(void *pvParameters);

#endif
