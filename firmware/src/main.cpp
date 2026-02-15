#define LGFX_AUTODETECT
#include <LovyanGFX.hpp>
#include <lvgl.h>
#include "lv_conf.h"
#include "ui.h"
#include "sensors.h"
#include "relay.h"
#include "relay.h"
#include "network_manager.h"

// Instance is created automatically by LGFX_AUTODETECT
static LGFX tft;

// --- 2. LVGL FLUSH CALLBACK ---
static const uint16_t screenWidth  = 320;
static const uint16_t screenHeight = 240;
static lv_disp_draw_buf_t draw_buf;
static lv_color_t buf[screenWidth * 10]; // Buffer for 10 lines

void my_disp_flush(lv_disp_drv_t *disp, const lv_area_t *area, lv_color_t *color_p) {
    uint32_t w = (area->x2 - area->x1 + 1);
    uint32_t h = (area->y2 - area->y1 + 1);

    if (tft.getStartCount() == 0) {
        tft.endWrite();
    }

    tft.pushImageDMA(area->x1, area->y1, w, h, (lgfx::rgb565_t*)&color_p->full);

    lv_disp_flush_ready(disp);
}

void my_touchpad_read(lv_indev_drv_t *indev_driver, lv_indev_data_t *data) {
    uint16_t touchX, touchY;
    bool touched = tft.getTouch(&touchX, &touchY);
    if (touched) {
        data->state = LV_INDEV_STATE_PR;
        data->point.x = touchX;
        data->point.y = touchY;
        Serial.printf("Touch: X=%d, Y=%d\n", touchX, touchY);
    } else {
        data->state = LV_INDEV_STATE_REL;
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("--- AUTO-DETECT START ---");

    // 1. FORCE POWER (The "Secret" Switch)
    // GPIO 46 is LCD Power, 47 is Backlight (Box-3)
    pinMode(46, OUTPUT); digitalWrite(46, HIGH); 
    pinMode(47, OUTPUT); digitalWrite(47, HIGH);
    pinMode(45, OUTPUT); digitalWrite(45, HIGH); // Just in case
    delay(100);

    // Initialize Network (WiFi + MQTT)
    network_init();



    // 2. Init Autodetected Driver
    tft.init();
    tft.setRotation(1);
    tft.setBrightness(255);
    
    // 3. Visual Confirmation
    tft.fillScreen(TFT_RED);
    delay(500);
    tft.fillScreen(TFT_GREEN);
    delay(500);
    tft.fillScreen(TFT_BLUE);
    delay(500);
    tft.fillScreen(TFT_BLACK);
    
    // 4. Init LVGL
    lv_init();
    lv_disp_draw_buf_init(&draw_buf, buf, NULL, screenWidth * 10);
    static lv_disp_drv_t disp_drv;
    lv_disp_drv_init(&disp_drv);
    disp_drv.hor_res = screenWidth;
    disp_drv.ver_res = screenHeight;
    disp_drv.flush_cb = my_disp_flush;
    disp_drv.draw_buf = &draw_buf;
    lv_disp_drv_register(&disp_drv);

    static lv_indev_drv_t indev_drv;
    lv_indev_drv_init(&indev_drv);
    indev_drv.type = LV_INDEV_TYPE_POINTER;
    indev_drv.read_cb = my_touchpad_read;
    lv_indev_drv_register(&indev_drv);

    // Initialize Relay
    relay_init();

    // Initialize Sensors
    sensors_init();

    // Initialize Relay -> Removed duplicate call


    ui_init(); // Back to Business
    Serial.println("UI Started");
}

void loop() {
    lv_timer_handler();
    
    // Handle Network (Reconnects if needed)
    network_loop(); 

    // Publish Telemetry every 2 seconds
    static unsigned long last_pub = 0;
    if (millis() - last_pub > 2000) {
        last_pub = millis();
        network_publish_telemetry(g_voltage, g_current, g_power, g_status);
    }

    delay(5);
}
