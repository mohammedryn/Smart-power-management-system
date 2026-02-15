#ifndef RELAY_H
#define RELAY_H

#include <Arduino.h>

#define PIN_RELAY 40 // Or G40

void relay_init();
void relay_on();
void relay_off();
bool is_relay_on();

#endif
