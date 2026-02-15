#ifndef UI_H
#define UI_H

#include <lvgl.h>

// UI Initialization
void ui_init();

// Update functions (to be called from main loop or tasks)
// Update functions (to be called from main loop or tasks)
void ui_update_val_1(float val);
void ui_update_val_2(float val);
void ui_update_val_3(float val);
void ui_update_status(const char* status);
void ui_update_chart(int* data, int len);

// Navigation
void ui_show_main();
void ui_show_chart();

// Special Modes
void ui_init_apology();

#endif
