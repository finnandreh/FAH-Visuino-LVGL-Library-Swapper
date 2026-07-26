#pragma once

#include <Arduino.h>

namespace waveshare43_example {

constexpr int display_width = 800;
constexpr int display_height = 480;

void begin();
void loop();
bool is_ready();
const char* last_error();
bool set_test_slider_value(int32_t value);
int32_t get_test_slider_value();
bool take_test_slider_change();
bool take_touch_button_click();
uint32_t get_touch_button_count();
bool set_pause_state(bool paused);
bool get_pause_state();
bool take_pause_state_change();
bool set_sine_gauge_value(int32_t value);
int32_t get_sine_gauge_value();

}  // namespace waveshare43_example
