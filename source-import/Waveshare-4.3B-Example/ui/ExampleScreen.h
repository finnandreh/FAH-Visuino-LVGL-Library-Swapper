#pragma once

#include <lvgl.h>

extern lv_obj_t* ui_title_label;
extern lv_obj_t* ui_driver_status_label;
extern lv_obj_t* ui_touch_status_label;
extern lv_obj_t* ui_touch_button;
extern lv_obj_t* ui_touch_button_label;
extern lv_obj_t* ui_touch_count_label;
extern lv_obj_t* ui_test_slider;
extern lv_obj_t* ui_slider_value_label;
extern lv_obj_t* ui_sine_gauge;
extern lv_meter_indicator_t* ui_sine_gauge_needle;
extern lv_obj_t* ui_sine_gauge_value_label;

void example_screen_create();
bool example_screen_take_touch_button_click();
uint32_t example_screen_get_touch_button_count();
bool example_screen_set_pause_state(bool paused);
bool example_screen_get_pause_state();
bool example_screen_take_pause_state_change();
bool example_screen_set_test_slider_value(int32_t value);
int32_t example_screen_get_test_slider_value();
bool example_screen_take_test_slider_change();
bool example_screen_set_sine_gauge_value(int32_t value);
int32_t example_screen_get_sine_gauge_value();
