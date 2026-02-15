#ifndef NETWORK_MANAGER_H
#define NETWORK_MANAGER_H

#include <Arduino.h>

void network_init();
void network_loop();
bool network_publish(const char* topic, const char* payload);
void network_publish_telemetry(float voltage, float current, float power, const char* status);

#endif
