#include "ui.h"
#include <Arduino.h>

// Global Objects
lv_obj_t * label_val_1;
lv_obj_t * label_val_2;
lv_obj_t * label_val_3;
lv_obj_t * label_status;

// Futuristic Colors
#define COLOR_BG      lv_color_hex(0x050505)
#define COLOR_CYAN    lv_color_hex(0x00f2fe)
#define COLOR_PINK    lv_color_hex(0xff0055)
#define COLOR_GREEN   lv_color_hex(0x00ff88)
#define COLOR_GLASS   lv_color_hex(0x1a1a1a)
#define COLOR_BORDER  lv_color_hex(0x333333)

static lv_style_t style_card;
static lv_style_t style_text_large;
static lv_style_t style_text_muted;
static lv_style_t style_text_neon;

void init_styles() {
    // Glassmorphism Card Style
    lv_style_init(&style_card);
    lv_style_set_bg_color(&style_card, COLOR_GLASS);
    lv_style_set_bg_opa(&style_card, LV_OPA_60);
    lv_style_set_radius(&style_card, 12);
    lv_style_set_border_width(&style_card, 1);
    lv_style_set_border_color(&style_card, COLOR_BORDER);
    lv_style_set_border_opa(&style_card, LV_OPA_40);
    lv_style_set_pad_all(&style_card, 8);
    // Subtle glow/shadow if possible (LVGL 8.3 supports shadow)
    lv_style_set_shadow_width(&style_card, 10);
    lv_style_set_shadow_color(&style_card, lv_color_black());
    lv_style_set_shadow_opa(&style_card, LV_OPA_40);

    // Large Value Style
    lv_style_init(&style_text_large);
    lv_style_set_text_font(&style_text_large, &lv_font_montserrat_28);
    lv_style_set_text_color(&style_text_large, lv_color_white());
    lv_style_set_text_letter_space(&style_text_large, 1);

    // Muted Label Style
    lv_style_init(&style_text_muted);
    lv_style_set_text_font(&style_text_muted, &lv_font_montserrat_14);
    lv_style_set_text_color(&style_text_muted, lv_color_hex(0x888888));
    lv_style_set_text_letter_space(&style_text_muted, 2);

    // Neon Status Style
    lv_style_init(&style_text_neon);
    lv_style_set_text_font(&style_text_neon, &lv_font_montserrat_14);
    lv_style_set_text_color(&style_text_neon, COLOR_CYAN);
}

// Screens
lv_obj_t * screen_main;
lv_obj_t * screen_chart;

// Chart Global
lv_obj_t * chart;
lv_chart_series_t * ser1;

// Forward Declarations
void cb_btn_to_chart(lv_event_t * e);
void cb_btn_to_main(lv_event_t * e);
void ui_init_animations();

lv_obj_t* create_card(lv_obj_t* parent, const char* title, const char* initial_val, lv_color_t accent_color) {
    lv_obj_t* card = lv_obj_create(parent);
    lv_obj_add_style(card, &style_card, 0);
    lv_obj_set_size(card, 148, 85); 
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(card, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    // Accent line at the top
    lv_obj_t* line = lv_obj_create(card);
    lv_obj_set_size(line, 40, 3);
    lv_obj_set_style_bg_color(line, accent_color, 0);
    lv_obj_set_style_border_width(line, 0, 0);
    lv_obj_set_style_radius(line, 2, 0);
    lv_obj_align(line, LV_ALIGN_TOP_MID, 0, -5);

    lv_obj_t* lbl_title = lv_label_create(card);
    lv_label_set_text(lbl_title, title);
    lv_obj_add_style(lbl_title, &style_text_muted, 0);

    lv_obj_t* lbl_val = lv_label_create(card);
    lv_label_set_text(lbl_val, initial_val);
    lv_obj_add_style(lbl_val, &style_text_large, 0);
    lv_obj_set_style_text_color(lbl_val, accent_color, 0);

    return lbl_val; 
}

void init_screen_main() {
    screen_main = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(screen_main, COLOR_BG, 0);

    // Background Decorative Orbs (Simulated with circles)
    lv_obj_t * orb1 = lv_obj_create(screen_main);
    lv_obj_set_size(orb1, 200, 200);
    lv_obj_set_style_radius(orb1, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(orb1, COLOR_CYAN, 0);
    lv_obj_set_style_bg_opa(orb1, LV_OPA_10, 0);
    lv_obj_set_style_border_width(orb1, 0, 0);
    lv_obj_align(orb1, LV_ALIGN_TOP_LEFT, -100, -100);

    lv_obj_t * orb2 = lv_obj_create(screen_main);
    lv_obj_set_size(orb2, 150, 150);
    lv_obj_set_style_radius(orb2, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(orb2, COLOR_PINK, 0);
    lv_obj_set_style_bg_opa(orb2, LV_OPA_10, 0);
    lv_obj_set_style_border_width(orb2, 0, 0);
    lv_obj_align(orb2, LV_ALIGN_BOTTOM_RIGHT, 50, 50);

    // 1. Grid Container
    lv_obj_t * cont = lv_obj_create(screen_main);
    lv_obj_set_size(cont, 320, 185); 
    lv_obj_set_layout(cont, LV_LAYOUT_FLEX);
    lv_obj_set_flex_flow(cont, LV_FLEX_FLOW_ROW_WRAP);
    lv_obj_set_flex_align(cont, LV_FLEX_ALIGN_SPACE_EVENLY, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_bg_opa(cont, 0, 0);
    lv_obj_set_style_pad_all(cont, 4, 0); 
    lv_obj_set_style_border_width(cont, 0, 0);

    // Row 1
    label_val_1 = create_card(cont, "POWER", "0.0 W", COLOR_CYAN);
    label_val_2 = create_card(cont, "CURRENT", "0.00 A", COLOR_PINK);

    // Row 2
    label_val_3 = create_card(cont, "VOLTAGE", "230 V", lv_color_white());
    label_status = create_card(cont, "STATUS", "ACTIVE", COLOR_GREEN);

    // 2. Waveform Button (Bottom)
    lv_obj_t * btn = lv_btn_create(screen_main);
    lv_obj_set_size(btn, 220, 40); 
    lv_obj_align(btn, LV_ALIGN_BOTTOM_MID, 0, -8); 
    lv_obj_add_style(btn, &style_card, 0);
    lv_obj_set_style_bg_color(btn, COLOR_CYAN, 0);
    lv_obj_set_style_bg_opa(btn, LV_OPA_20, 0);
    lv_obj_set_style_border_color(btn, COLOR_CYAN, 0);
    lv_obj_set_style_border_opa(btn, LV_OPA_60, 0);
    lv_obj_add_event_cb(btn, cb_btn_to_chart, LV_EVENT_CLICKED, NULL);

    lv_obj_t * lbl = lv_label_create(btn);
    lv_label_set_text(lbl, "NEURAL WAVEFORM");
    lv_obj_add_style(lbl, &style_text_muted, 0);
    lv_obj_set_style_text_color(lbl, COLOR_CYAN, 0);
    lv_obj_center(lbl);
}

void init_screen_chart() {
    screen_chart = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(screen_chart, COLOR_BG, 0);

    // 1. The Chart
    chart = lv_chart_create(screen_chart);
    lv_obj_set_size(chart, 300, 180);
    lv_obj_align(chart, LV_ALIGN_TOP_MID, 0, 10);
    lv_obj_set_style_bg_color(chart, COLOR_GLASS, 0);
    lv_obj_set_style_border_color(chart, COLOR_BORDER, 0);
    lv_obj_set_style_border_opa(chart, LV_OPA_40, 0);
    
    lv_chart_set_type(chart, LV_CHART_TYPE_LINE); 
    lv_chart_set_point_count(chart, 50); 
    lv_chart_set_range(chart, LV_CHART_AXIS_PRIMARY_Y, 0, 4096);
    lv_obj_set_style_line_width(chart, 3, LV_PART_ITEMS);
    
    // Add Series
    ser1 = lv_chart_add_series(chart, COLOR_CYAN, LV_CHART_AXIS_PRIMARY_Y);

    // 2. Back Button
    lv_obj_t * btn_back = lv_btn_create(screen_chart);
    lv_obj_set_size(btn_back, 120, 35); 
    lv_obj_align(btn_back, LV_ALIGN_BOTTOM_MID, 0, -10); 
    lv_obj_add_style(btn_back, &style_card, 0);
    lv_obj_set_style_bg_color(btn_back, COLOR_PINK, 0);
    lv_obj_set_style_bg_opa(btn_back, LV_OPA_20, 0);
    lv_obj_set_style_border_color(btn_back, COLOR_PINK, 0);
    lv_obj_set_style_border_opa(btn_back, LV_OPA_60, 0);
    lv_obj_add_event_cb(btn_back, cb_btn_to_main, LV_EVENT_CLICKED, NULL);

    lv_obj_t * lbl_back = lv_label_create(btn_back);
    lv_label_set_text(lbl_back, "< BACK");
    lv_obj_add_style(lbl_back, &style_text_muted, 0);
    lv_obj_set_style_text_color(lbl_back, COLOR_PINK, 0);
    lv_obj_center(lbl_back);
}

// Event Callbacks
void cb_btn_to_chart(lv_event_t * e) {
    ui_show_chart();
}

void cb_btn_to_main(lv_event_t * e) {
    ui_show_main();
}

void ui_show_main() {
    lv_scr_load(screen_main);
}

void ui_show_chart() {
    lv_scr_load(screen_chart);
}

void ui_init() {
    init_styles();
    init_screen_main();
    init_screen_chart();
    ui_init_animations();
    ui_show_main();
}

void ui_update_chart(int* data, int len) {
    if(!chart || !ser1) return;
    
    int min_val = 4096;
    int max_val = 0;

    // 1. Push data & Find Ranges
    for(int i=0; i<len; i++) {
        if(data[i] < min_val) min_val = data[i];
        if(data[i] > max_val) max_val = data[i];
        lv_chart_set_next_value(chart, ser1, data[i]);
    }

    // 2. OSCILLOSCOPE AUTO-SCALE LOGIC
    int diff = max_val - min_val;
    if (diff < 300) {
        int mid = (min_val + max_val) / 2;
        if(mid == 0) mid = 2048; 
        min_val = mid - 150;
        max_val = mid + 150;
    } else {
        int pad = diff * 0.1;
        min_val -= pad;
        max_val += pad;
    }

    if(min_val < 0) min_val = 0;
    if(max_val > 4095) max_val = 4095;

    lv_chart_set_range(chart, LV_CHART_AXIS_PRIMARY_Y, min_val, max_val);
    lv_chart_refresh(chart);
}

void ui_update_val_1(float val) {
    if(label_val_1) {
        String s = String(val, 1) + " W";
        lv_label_set_text(label_val_1, s.c_str());
    }
}

void ui_update_val_2(float val) {
    if(label_val_2) {
        String s = String(val, 2) + " A";
        lv_label_set_text(label_val_2, s.c_str());
    }
}

void ui_update_val_3(float val) {
    if(label_val_3) {
        String s = String(val, 0) + " V";
        lv_label_set_text(label_val_3, s.c_str());
    }
}

static void anim_orb_opa(void * var, int32_t v) {
    lv_obj_set_style_bg_opa((lv_obj_t*)var, v, 0);
}

void ui_init_animations() {
    // Breathing Orbs
    lv_obj_t * orb1 = lv_obj_get_child(screen_main, 0);
    lv_obj_t * orb2 = lv_obj_get_child(screen_main, 1);

    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, orb1);
    lv_anim_set_values(&a, 10, 50); // Use raw values for opacity (0-255)
    lv_anim_set_time(&a, 3000);
    lv_anim_set_playback_time(&a, 3000);
    lv_anim_set_repeat_count(&a, LV_ANIM_REPEAT_INFINITE);
    lv_anim_set_exec_cb(&a, anim_orb_opa);
    lv_anim_start(&a);

    lv_anim_set_var(&a, orb2);
    lv_anim_set_time(&a, 3500); // Slightly different timing for organic feel
    lv_anim_set_playback_time(&a, 3500);
    lv_anim_start(&a);
}

String current_status = "ACTIVE";
void ui_update_status(const char* status) {
    if(label_status) {
        lv_label_set_text(label_status, status);
        String s = String(status);
        if(s.indexOf("FAULT") >= 0) {
            lv_obj_set_style_text_color(label_status, COLOR_PINK, 0);
        } else {
            lv_obj_set_style_text_color(label_status, COLOR_GREEN, 0);
        }
    }
}

// --- APOLOGY UI UI (Keep for legacy/fun) ---
static void anim_heart_pulse(void * var, int32_t val) {
    lv_obj_set_style_transform_zoom((lv_obj_t*)var, val, 0);
}

void ui_init_apology() {
    lv_obj_t * scr = lv_scr_act();
    lv_obj_set_style_bg_color(scr, lv_color_hex(0xffecf0), 0); // Light Pink Background

    // 1. The Message
    lv_obj_t * label_msg = lv_label_create(scr);
    lv_label_set_text(label_msg, "I'm sorry ynv\nI love you\nso much!");
    lv_label_set_long_mode(label_msg, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(label_msg, 280);
    lv_obj_set_style_text_align(label_msg, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(label_msg, lv_palette_main(LV_PALETTE_RED), 0);
    lv_obj_set_style_text_font(label_msg, &lv_font_montserrat_28, 0);
    lv_obj_align(label_msg, LV_ALIGN_CENTER, 0, -40);

    // 2. The Heart
    lv_obj_t * label_heart = lv_label_create(scr);
    lv_label_set_text(label_heart, ":)"); 
    lv_obj_set_style_text_font(label_heart, &lv_font_montserrat_28, 0); // Use 28 (Available)
    lv_obj_set_style_text_color(label_heart, lv_palette_main(LV_PALETTE_RED), 0);
    lv_obj_align(label_heart, LV_ALIGN_CENTER, 0, 50);

    // 3. Pulse Animation
    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, label_heart);
    lv_anim_set_values(&a, 256, 300); // Zoom from 100% to 120%
    lv_anim_set_time(&a, 500);
    lv_anim_set_playback_time(&a, 500);
    lv_anim_set_repeat_count(&a, LV_ANIM_REPEAT_INFINITE);
    lv_anim_set_exec_cb(&a, anim_heart_pulse);
    lv_anim_start(&a);
}