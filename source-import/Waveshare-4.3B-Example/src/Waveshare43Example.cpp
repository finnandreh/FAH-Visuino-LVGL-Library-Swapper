#include "Waveshare43Device.h"

#include <esp_display_panel.hpp>
#include <lvgl.h>

#include "lvgl_v8_port.h"
#include "ui/ExampleScreen.h"

using namespace esp_panel::board;

namespace waveshare43_example {
namespace {

Board* board = nullptr;
bool ready = false;
const char* error_message = "Not initialized";
uint32_t last_heartbeat_ms = 0;

void fail(const char* message) {
  ready = false;
  error_message = message;
  Serial0.print("[Waveshare 4.3B] ERROR: ");
  Serial0.println(message);
}

}  // namespace

void begin() {
  if (ready) {
    return;
  }

  Serial0.begin(115200);
  delay(250);
  Serial0.println();
  Serial0.println("[Waveshare 4.3B] Starting LCD, touch, expander and LVGL");

  board = new Board();
  if (board == nullptr) {
    fail("Unable to allocate the board driver");
    return;
  }

  board->init();
  if (board->getLCD() == nullptr) {
    fail("ST7262/RGB LCD driver was not created");
    return;
  }
  if (board->getTouch() == nullptr) {
    fail("GT911 touch driver was not created");
    return;
  }
  if (board->getIO_Expander() == nullptr) {
    fail("CH422G I/O expander driver was not created");
    return;
  }
  if (board->getBacklight() == nullptr) {
    fail("CH422G backlight driver was not created");
    return;
  }

  if (!board->begin()) {
    fail("Board driver initialization failed");
    return;
  }
  if (!board->getBacklight()->on()) {
    fail("Backlight could not be switched on");
    return;
  }
  if (!lvgl_port_init(board->getLCD(), board->getTouch())) {
    fail("LVGL display or touch registration failed");
    return;
  }
  if (!lvgl_port_lock(-1)) {
    fail("LVGL mutex could not be locked");
    return;
  }

  example_screen_create();
  lvgl_port_unlock();

  ready = true;
  error_message = "";
  last_heartbeat_ms = millis();
  Serial0.println("[Waveshare 4.3B] READY: 800x480 RGB, GT911 touch, CH422G and backlight");
}

void loop() {
  if (!ready) {
    delay(20);
    return;
  }

  if (lvgl_port_lock(5)) {
    lv_timer_handler();
    lvgl_port_unlock();
  }

  const uint32_t now = millis();
  if (now - last_heartbeat_ms >= 5000) {
    last_heartbeat_ms = now;
    Serial0.printf("[Waveshare 4.3B] alive: %lu ms\n",
                   static_cast<unsigned long>(now));
  }
  delay(5);
}

bool is_ready() {
  return ready;
}

const char* last_error() {
  return error_message;
}

bool set_test_slider_value(int32_t value) {
  if (!ready || !lvgl_port_lock(20)) {
    return false;
  }

  const bool updated = example_screen_set_test_slider_value(value);
  lvgl_port_unlock();
  return updated;
}

int32_t get_test_slider_value() {
  if (!ready || !lvgl_port_lock(20)) {
    return 0;
  }

  const int32_t value = example_screen_get_test_slider_value();
  lvgl_port_unlock();
  return value;
}

bool take_test_slider_change() {
  if (!ready || !lvgl_port_lock(20)) {
    return false;
  }

  const bool changed = example_screen_take_test_slider_change();
  lvgl_port_unlock();
  return changed;
}

bool take_touch_button_click() {
  if (!ready || !lvgl_port_lock(20)) {
    return false;
  }

  const bool clicked = example_screen_take_touch_button_click();
  lvgl_port_unlock();
  return clicked;
}

uint32_t get_touch_button_count() {
  if (!ready || !lvgl_port_lock(20)) {
    return 0;
  }

  const uint32_t count = example_screen_get_touch_button_count();
  lvgl_port_unlock();
  return count;
}

bool set_pause_state(bool paused) {
  if (!ready || !lvgl_port_lock(20)) {
    return false;
  }

  const bool updated = example_screen_set_pause_state(paused);
  lvgl_port_unlock();
  return updated;
}

bool get_pause_state() {
  if (!ready || !lvgl_port_lock(20)) {
    return false;
  }

  const bool paused = example_screen_get_pause_state();
  lvgl_port_unlock();
  return paused;
}

bool take_pause_state_change() {
  if (!ready || !lvgl_port_lock(20)) {
    return false;
  }

  const bool changed = example_screen_take_pause_state_change();
  lvgl_port_unlock();
  return changed;
}

bool set_sine_gauge_value(int32_t value) {
  if (!ready || !lvgl_port_lock(20)) {
    return false;
  }

  const bool updated = example_screen_set_sine_gauge_value(value);
  lvgl_port_unlock();
  return updated;
}

int32_t get_sine_gauge_value() {
  if (!ready || !lvgl_port_lock(20)) {
    return 0;
  }

  const int32_t value = example_screen_get_sine_gauge_value();
  lvgl_port_unlock();
  return value;
}

}  // namespace waveshare43_example
