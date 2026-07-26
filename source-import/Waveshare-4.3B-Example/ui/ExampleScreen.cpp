#include "ExampleScreen.h"

#include <Arduino.h>
#include <lvgl.h>

lv_obj_t* ui_title_label = nullptr;
lv_obj_t* ui_driver_status_label = nullptr;
lv_obj_t* ui_touch_status_label = nullptr;
lv_obj_t* ui_touch_button = nullptr;
lv_obj_t* ui_touch_button_label = nullptr;
lv_obj_t* ui_touch_count_label = nullptr;
lv_obj_t* ui_test_slider = nullptr;
lv_obj_t* ui_slider_value_label = nullptr;
lv_obj_t* ui_sine_gauge = nullptr;
lv_meter_indicator_t* ui_sine_gauge_needle = nullptr;
lv_obj_t* ui_sine_gauge_value_label = nullptr;

namespace {

lv_color_t color(uint32_t value) {
  return lv_color_hex(value);
}

uint32_t touch_count = 0;
bool touch_button_click_pending = false;
bool pause_state = false;
bool pause_state_change_pending = false;
bool test_slider_change_pending = false;
bool programmatic_slider_update = false;
int32_t sine_gauge_value = 50;

int32_t clamp_percent(int32_t value) {
  if (value < 0) {
    return 0;
  }
  if (value > 100) {
    return 100;
  }
  return value;
}

void update_pause_visuals() {
  if (ui_touch_button == nullptr ||
      ui_touch_button_label == nullptr ||
      ui_touch_count_label == nullptr) {
    return;
  }

  const uint32_t accent = pause_state ? 0xFF9F43 : 0x4FA3FF;
  lv_label_set_text(ui_touch_button_label,
                    pause_state ? "PAUSED - TAP TO RESUME"
                                : "RUNNING - TAP TO PAUSE");
  lv_label_set_text_fmt(ui_touch_count_label,
                        "%s | button clicks: %lu",
                        pause_state ? "Paused" : "Running",
                        static_cast<unsigned long>(touch_count));
  lv_obj_set_style_bg_color(ui_touch_button, color(accent), LV_PART_MAIN);
  lv_obj_set_style_shadow_color(ui_touch_button, color(accent), LV_PART_MAIN);
}

void update_touch_position(lv_event_t* event, const char* source) {
  lv_indev_t* input = lv_event_get_indev(event);
  if (input == nullptr) {
    lv_label_set_text_fmt(ui_touch_status_label, "%s received", source);
    Serial0.printf("[Waveshare 4.3B] %s received\n", source);
    return;
  }

  lv_point_t point{};
  lv_indev_get_point(input, &point);
  lv_label_set_text_fmt(ui_touch_status_label,
                        "%s at x=%d, y=%d",
                        source,
                        static_cast<int>(point.x),
                        static_cast<int>(point.y));
  Serial0.printf("[Waveshare 4.3B] %s at x=%d, y=%d\n",
                 source,
                 static_cast<int>(point.x),
                 static_cast<int>(point.y));
}

void touch_button_event(lv_event_t* event) {
  if (lv_event_get_code(event) != LV_EVENT_CLICKED) {
    return;
  }

  ++touch_count;
  touch_button_click_pending = true;
  pause_state = !pause_state;
  pause_state_change_pending = true;
  update_pause_visuals();
  update_touch_position(event, "Button touch");
}

void slider_event(lv_event_t* event) {
  if (lv_event_get_code(event) != LV_EVENT_VALUE_CHANGED) {
    return;
  }

  const int value = lv_slider_get_value(ui_test_slider);
  lv_label_set_text_fmt(ui_slider_value_label, "%d %%", value);
  if (!programmatic_slider_update) {
    test_slider_change_pending = true;
    Serial0.printf("[Waveshare 4.3B] Sine speed: %d %%\n", value);
    update_touch_position(event, "Speed slider");
  }
}

lv_obj_t* make_card(lv_obj_t* parent, int x, int y, int width, int height) {
  lv_obj_t* card = lv_obj_create(parent);
  lv_obj_set_pos(card, x, y);
  lv_obj_set_size(card, width, height);
  lv_obj_set_style_radius(card, 18, LV_PART_MAIN);
  lv_obj_set_style_bg_color(card, color(0x101A29), LV_PART_MAIN);
  lv_obj_set_style_bg_opa(card, LV_OPA_COVER, LV_PART_MAIN);
  lv_obj_set_style_border_color(card, color(0x263C56), LV_PART_MAIN);
  lv_obj_set_style_border_width(card, 1, LV_PART_MAIN);
  lv_obj_set_style_pad_all(card, 18, LV_PART_MAIN);
  lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);
  return card;
}

lv_obj_t* make_status_row(lv_obj_t* parent,
                          const char* title,
                          const char* detail,
                          int y) {
  lv_obj_t* dot = lv_obj_create(parent);
  lv_obj_set_pos(dot, 2, y + 6);
  lv_obj_set_size(dot, 12, 12);
  lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, LV_PART_MAIN);
  lv_obj_set_style_bg_color(dot, color(0x00D7B8), LV_PART_MAIN);
  lv_obj_set_style_border_width(dot, 0, LV_PART_MAIN);
  lv_obj_clear_flag(dot, LV_OBJ_FLAG_SCROLLABLE);

  lv_obj_t* label = lv_label_create(parent);
  lv_label_set_text_fmt(label, "%s\n%s", title, detail);
  lv_obj_set_pos(label, 26, y);
  lv_obj_set_style_text_color(label, color(0xF4F8FC), LV_PART_MAIN);
  lv_obj_set_style_text_font(label, &lv_font_montserrat_14, LV_PART_MAIN);
  return label;
}

}  // namespace

void example_screen_create() {
  lv_obj_t* screen = lv_scr_act();
  lv_obj_clear_flag(screen, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_style_bg_color(screen, color(0x07101B), LV_PART_MAIN);
  lv_obj_set_style_bg_grad_color(screen, color(0x0E2033), LV_PART_MAIN);
  lv_obj_set_style_bg_grad_dir(screen, LV_GRAD_DIR_HOR, LV_PART_MAIN);

  lv_obj_t* eyebrow = lv_label_create(screen);
  lv_label_set_text(eyebrow, "LVGL LIBRARY SWAPPER / HARDWARE TEST");
  lv_obj_set_pos(eyebrow, 28, 18);
  lv_obj_set_style_text_color(eyebrow, color(0x6FA8D8), LV_PART_MAIN);
  lv_obj_set_style_text_font(eyebrow, &lv_font_montserrat_12, LV_PART_MAIN);

  ui_title_label = lv_label_create(screen);
  lv_label_set_text(ui_title_label, "Waveshare 4.3B is ready");
  lv_obj_set_pos(ui_title_label, 26, 40);
  lv_obj_set_style_text_color(ui_title_label, color(0xF4F8FC), LV_PART_MAIN);
  lv_obj_set_style_text_font(ui_title_label, &lv_font_montserrat_30, LV_PART_MAIN);

  lv_obj_t* ready_badge = lv_obj_create(screen);
  lv_obj_set_pos(ready_badge, 603, 26);
  lv_obj_set_size(ready_badge, 169, 42);
  lv_obj_set_style_radius(ready_badge, 21, LV_PART_MAIN);
  lv_obj_set_style_bg_color(ready_badge, color(0x0B3C3A), LV_PART_MAIN);
  lv_obj_set_style_border_color(ready_badge, color(0x00D7B8), LV_PART_MAIN);
  lv_obj_set_style_border_width(ready_badge, 1, LV_PART_MAIN);
  lv_obj_clear_flag(ready_badge, LV_OBJ_FLAG_SCROLLABLE);

  lv_obj_t* ready_label = lv_label_create(ready_badge);
  lv_label_set_text(ready_label, "DRIVERS READY");
  lv_obj_set_style_text_color(ready_label, color(0x74F6E2), LV_PART_MAIN);
  lv_obj_set_style_text_font(ready_label, &lv_font_montserrat_14, LV_PART_MAIN);
  lv_obj_center(ready_label);

  lv_obj_t* touch_card = make_card(screen, 26, 91, 493, 340);

  lv_obj_t* touch_title = lv_label_create(touch_card);
  lv_label_set_text(touch_title, "Visuino sine controls");
  lv_obj_set_pos(touch_title, 2, 0);
  lv_obj_set_style_text_color(touch_title, color(0xF4F8FC), LV_PART_MAIN);
  lv_obj_set_style_text_font(touch_title, &lv_font_montserrat_26, LV_PART_MAIN);

  ui_touch_status_label = lv_label_create(touch_card);
  lv_label_set_text(ui_touch_status_label,
                    "Slider = speed command | button = pause command");
  lv_obj_set_pos(ui_touch_status_label, 2, 36);
  lv_obj_set_width(ui_touch_status_label, 448);
  lv_obj_set_style_text_color(ui_touch_status_label, color(0x9BB0C5), LV_PART_MAIN);
  lv_obj_set_style_text_font(ui_touch_status_label, &lv_font_montserrat_14, LV_PART_MAIN);

  ui_touch_button = lv_btn_create(touch_card);
  lv_obj_set_pos(ui_touch_button, 2, 72);
  lv_obj_set_size(ui_touch_button, 448, 72);
  lv_obj_set_style_radius(ui_touch_button, 14, LV_PART_MAIN);
  lv_obj_set_style_bg_color(ui_touch_button, color(0x4FA3FF), LV_PART_MAIN);
  lv_obj_set_style_shadow_color(ui_touch_button, color(0x4FA3FF), LV_PART_MAIN);
  lv_obj_set_style_shadow_opa(ui_touch_button, LV_OPA_30, LV_PART_MAIN);
  lv_obj_set_style_shadow_width(ui_touch_button, 18, LV_PART_MAIN);
  lv_obj_add_event_cb(ui_touch_button,
                      touch_button_event,
                      LV_EVENT_CLICKED,
                      nullptr);

  ui_touch_button_label = lv_label_create(ui_touch_button);
  lv_label_set_text(ui_touch_button_label, "RUNNING - TAP TO PAUSE");
  lv_obj_set_style_text_color(ui_touch_button_label, color(0xFFFFFF), LV_PART_MAIN);
  lv_obj_set_style_text_font(ui_touch_button_label, &lv_font_montserrat_16, LV_PART_MAIN);
  lv_obj_center(ui_touch_button_label);

  ui_touch_count_label = lv_label_create(touch_card);
  lv_label_set_text(ui_touch_count_label, "Running | button clicks: 0");
  lv_obj_set_pos(ui_touch_count_label, 2, 158);
  lv_obj_set_style_text_color(ui_touch_count_label, color(0xDCE8F3), LV_PART_MAIN);
  lv_obj_set_style_text_font(ui_touch_count_label, &lv_font_montserrat_14, LV_PART_MAIN);

  lv_obj_t* slider_title = lv_label_create(touch_card);
  lv_label_set_text(slider_title, "Sine speed command");
  lv_obj_set_pos(slider_title, 2, 198);
  lv_obj_set_style_text_color(slider_title, color(0x9BB0C5), LV_PART_MAIN);

  ui_slider_value_label = lv_label_create(touch_card);
  lv_label_set_text(ui_slider_value_label, "50 %");
  lv_obj_align(ui_slider_value_label, LV_ALIGN_TOP_RIGHT, -2, 198);
  lv_obj_set_style_text_color(ui_slider_value_label, color(0x74F6E2), LV_PART_MAIN);

  ui_test_slider = lv_slider_create(touch_card);
  lv_slider_set_range(ui_test_slider, 0, 100);
  lv_slider_set_value(ui_test_slider, 50, LV_ANIM_OFF);
  lv_obj_set_pos(ui_test_slider, 2, 240);
  lv_obj_set_size(ui_test_slider, 448, 18);
  lv_obj_set_style_bg_color(ui_test_slider, color(0x263C56), LV_PART_MAIN);
  lv_obj_set_style_bg_color(ui_test_slider, color(0x00D7B8), LV_PART_INDICATOR);
  lv_obj_set_style_bg_color(ui_test_slider, color(0xF4F8FC), LV_PART_KNOB);
  lv_obj_set_style_pad_all(ui_test_slider, 7, LV_PART_KNOB);
  lv_obj_add_event_cb(ui_test_slider,
                      slider_event,
                      LV_EVENT_VALUE_CHANGED,
                      nullptr);

  lv_obj_t* speed_help = lv_label_create(touch_card);
  lv_label_set_text(speed_help,
                    "Read speed in Visuino, generate 0-100, then send the result to the gauge.");
  lv_obj_set_pos(speed_help, 2, 282);
  lv_obj_set_width(speed_help, 448);
  lv_obj_set_style_text_color(speed_help, color(0x6F8498), LV_PART_MAIN);
  lv_obj_set_style_text_font(speed_help, &lv_font_montserrat_12, LV_PART_MAIN);

  lv_obj_t* gauge_card = make_card(screen, 537, 91, 235, 340);

  lv_obj_t* gauge_title = lv_label_create(gauge_card);
  lv_label_set_text(gauge_title, "Sine output");
  lv_obj_set_pos(gauge_title, 2, 0);
  lv_obj_set_style_text_color(gauge_title, color(0xF4F8FC), LV_PART_MAIN);
  lv_obj_set_style_text_font(gauge_title, &lv_font_montserrat_16, LV_PART_MAIN);

  lv_obj_t* gauge_subtitle = lv_label_create(gauge_card);
  lv_label_set_text(gauge_subtitle, "Visuino -> LVGL");
  lv_obj_set_pos(gauge_subtitle, 2, 24);
  lv_obj_set_style_text_color(gauge_subtitle, color(0x6FA8D8), LV_PART_MAIN);
  lv_obj_set_style_text_font(gauge_subtitle, &lv_font_montserrat_12, LV_PART_MAIN);

  ui_sine_gauge = lv_meter_create(gauge_card);
  lv_obj_set_pos(ui_sine_gauge, 5, 48);
  lv_obj_set_size(ui_sine_gauge, 190, 190);
  lv_obj_set_style_bg_color(ui_sine_gauge, color(0x07101B), LV_PART_MAIN);
  lv_obj_set_style_border_color(ui_sine_gauge, color(0x263C56), LV_PART_MAIN);
  lv_obj_set_style_border_width(ui_sine_gauge, 1, LV_PART_MAIN);
  lv_obj_clear_flag(ui_sine_gauge, LV_OBJ_FLAG_SCROLLABLE);

  lv_meter_scale_t* gauge_scale = lv_meter_add_scale(ui_sine_gauge);
  lv_meter_set_scale_ticks(ui_sine_gauge,
                           gauge_scale,
                           21,
                           2,
                           9,
                           color(0x526B82));
  lv_meter_set_scale_major_ticks(ui_sine_gauge,
                                 gauge_scale,
                                 5,
                                 4,
                                 14,
                                 color(0xDCE8F3),
                                 10);
  lv_meter_set_scale_range(ui_sine_gauge, gauge_scale, 0, 100, 270, 135);
  ui_sine_gauge_needle = lv_meter_add_needle_line(ui_sine_gauge,
                                                  gauge_scale,
                                                  4,
                                                  color(0x00D7B8),
                                                  -12);
  lv_meter_set_indicator_value(ui_sine_gauge, ui_sine_gauge_needle, 50);

  ui_sine_gauge_value_label = lv_label_create(ui_sine_gauge);
  lv_label_set_text(ui_sine_gauge_value_label, "50 %");
  lv_obj_set_style_text_color(ui_sine_gauge_value_label, color(0x74F6E2), LV_PART_MAIN);
  lv_obj_set_style_text_font(ui_sine_gauge_value_label, &lv_font_montserrat_26, LV_PART_MAIN);
  lv_obj_align(ui_sine_gauge_value_label, LV_ALIGN_CENTER, 0, 48);

  ui_driver_status_label = lv_label_create(gauge_card);
  lv_label_set_text(ui_driver_status_label,
                    "LVGL 8.4 | GT911\nST7262 | CH422G");
  lv_obj_set_pos(ui_driver_status_label, 2, 257);
  lv_obj_set_style_text_color(ui_driver_status_label, color(0x6FA8D8), LV_PART_MAIN);
  lv_obj_set_style_text_font(ui_driver_status_label, &lv_font_montserrat_12, LV_PART_MAIN);

  lv_obj_t* footer = lv_label_create(screen);
  lv_label_set_text(footer,
                    "UI -> Visuino: speed and pause | Visuino -> UI: sine value gauge");
  lv_obj_set_pos(footer, 28, 449);
  lv_obj_set_style_text_color(footer, color(0x6F8498), LV_PART_MAIN);
  lv_obj_set_style_text_font(footer, &lv_font_montserrat_12, LV_PART_MAIN);
}

bool example_screen_take_touch_button_click() {
  const bool clicked = touch_button_click_pending;
  touch_button_click_pending = false;
  return clicked;
}

uint32_t example_screen_get_touch_button_count() {
  return touch_count;
}

bool example_screen_set_pause_state(bool paused) {
  if (ui_touch_button == nullptr || ui_touch_button_label == nullptr) {
    return false;
  }

  pause_state = paused;
  update_pause_visuals();
  return true;
}

bool example_screen_get_pause_state() {
  return pause_state;
}

bool example_screen_take_pause_state_change() {
  const bool changed = pause_state_change_pending;
  pause_state_change_pending = false;
  return changed;
}

bool example_screen_set_test_slider_value(int32_t value) {
  if (ui_test_slider == nullptr || ui_slider_value_label == nullptr) {
    return false;
  }

  const int32_t clamped = clamp_percent(value);
  programmatic_slider_update = true;
  lv_slider_set_value(ui_test_slider, clamped, LV_ANIM_OFF);
  programmatic_slider_update = false;
  lv_label_set_text_fmt(ui_slider_value_label, "%ld %%",
                        static_cast<long>(clamped));
  return true;
}

int32_t example_screen_get_test_slider_value() {
  if (ui_test_slider == nullptr) {
    return 0;
  }
  return lv_slider_get_value(ui_test_slider);
}

bool example_screen_take_test_slider_change() {
  const bool changed = test_slider_change_pending;
  test_slider_change_pending = false;
  return changed;
}

bool example_screen_set_sine_gauge_value(int32_t value) {
  if (ui_sine_gauge == nullptr ||
      ui_sine_gauge_needle == nullptr ||
      ui_sine_gauge_value_label == nullptr) {
    return false;
  }

  sine_gauge_value = clamp_percent(value);
  lv_meter_set_indicator_value(ui_sine_gauge,
                               ui_sine_gauge_needle,
                               sine_gauge_value);
  lv_label_set_text_fmt(ui_sine_gauge_value_label,
                        "%ld %%",
                        static_cast<long>(sine_gauge_value));
  return true;
}

int32_t example_screen_get_sine_gauge_value() {
  return sine_gauge_value;
}
