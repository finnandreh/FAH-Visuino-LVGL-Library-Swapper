# Waveshare ESP32-S3 Touch LCD 4.3B Standalone Import

This is a complete LVGL 8.4 Arduino package for the exact Waveshare
`ESP32-S3-Touch-LCD-4.3B` board. It initializes:

- the 800 x 480 ST7262 RGB LCD;
- the GT911 capacitive touch controller and interrupt;
- the CH422G I/O expander and LCD/touch reset sequence;
- the CH422G EXIO2 backlight switch;
- the LVGL display buffer, flush callback, 2 ms tick, and touch input device;
- a visible Visuino bridge screen with a pause button, a 0-100 sine-speed
  slider, and a 0-100 speedometer-style sine gauge.

The `libraries` directory includes the complete setup-local versions used by
this project:

- LVGL 8.4.0;
- ESP32_Display_Panel 1.0.0, configured for
  `BOARD_WAVESHARE_ESP32_S3_TOUCH_LCD_4_3_B`;
- ESP32_IO_Expander 1.0.1;
- esp-lib-utils 0.1.2.

The screen backlight is a CH422G on/off output. The UI slider is a sine-speed
command and does not pretend that the board has PWM brightness control.

## Import into FAH Visuino LVGL Library Swapper

1. Start `FAH-Visuino-LVGL-Library-Swapper.exe`.
2. Create or select a client.
3. Create or select a project under that client.
4. Create a new setup/sketchbook folder or link an existing setup.
5. Choose **Validate Setup** and add only missing `Mitov` and optional
   `VisuinoPro` when offered.
6. Open **Device & Custom Code** and select **Standalone Import**.
7. Select this entire `Waveshare-4.3B-Example` folder.
8. Use `Waveshare43B` as the implementation library name.
9. Choose **Analyze & Import**, review the plan, close Visuino Pro, and confirm.
10. Validate and activate the setup.
11. Open **Visuino Custom Code** and copy the populated root INO when building
   the Custom Code component manually.
12. In Visuino, add a Custom Code component, open its Arduino Code
   Import/Parser, paste the complete INO there, and choose Parse. Review the
   separated includes/globals, initialization, and loop code before accepting
   it.
13. Open **UI Element Variables** to inspect and copy the exported Read API and
    Write API calls for the pause button, slider, gauge, and labels.

The portable demo release also supplies `FAH-Waveshare43-Demo.visuino` beside
the EXE. Open it after the Waveshare setup is imported, validated, and active.

## Visuino UI bridge

The display library owns the LVGL widgets and mutex protection. Visuino owns the
sine-wave generator and component wiring.

### Keep the namespace

Every project bridge function in this package belongs to the C++ namespace
`waveshare43_example`. Keep `waveshare43_example::` before the function name
whenever you use one in Visuino. The `::` tells C++ where the function lives.
Removing the namespace makes a complete bridge call such as
`waveshare43_example::set_test_slider_value(AValue);` fail to compile.

`AValue` is the value received by that Visuino Custom Code Input. Functions
whose names begin with `lv_` are global LVGL functions and do not use this
project namespace.

The suggested signal path is:

1. Read the 0-100 speed slider from Custom Code and map it to the Sine Integer
   Generator frequency you want.
2. Read the pause state from Custom Code. A true value means paused; invert it
   when the Visuino input expects `Enabled`.
3. Configure the Sine Integer Generator with amplitude `50` and offset `50` so
   its output is 0-100.
4. Connect that integer output to a Custom Code Integer Input whose code writes
   the value to the gauge.

Move the slider from a Custom Code Integer Input:

```cpp
waveshare43_example::set_test_slider_value(AValue);
```

The function clamps the incoming integer to 0-100, moves `ui_test_slider`, and
updates the visible value label while holding the LVGL mutex.

Read slider changes in the Custom Code loop:

```cpp
if (waveshare43_example::take_test_slider_change()) {
  Integer1.Send(waveshare43_example::get_test_slider_value());
}
```

Read the pause command:

```cpp
if (waveshare43_example::take_pause_state_change()) {
  Digital1.Send(waveshare43_example::get_pause_state());
}
```

If the destination is an `Enabled` input, send the inverse:

```cpp
Digital1.Send(!waveshare43_example::get_pause_state());
```

Move the gauge from the Sine Integer Generator output:

```cpp
waveshare43_example::set_sine_gauge_value(AValue);
```

Call this once per incoming sine value. It clamps the value to 0-100 and updates
the gauge needle, the numeric percentage label, and the stored readback value
together. Do not create a second input for the percentage label.

Output names such as `Integer1` and `Digital1` depend on the elements created in
the Visuino Custom Code component. `Send(...)` does not return a value.

The complete API and state contract is documented in
`docs/visuino-ui-control-contract.md` in the FAH Visuino LVGL Library Swapper
project.

## Arduino board settings

Use **ESP32S3 Dev Module** with:

- ESP32 Arduino core 3.3.10;
- Flash Size: 16 MB;
- Flash Mode: QIO 80 MHz;
- PSRAM: OPI PSRAM;
- Partition Scheme: 16 MB, 3 MB application (`app3M_fat9M_16MB`);
- USB CDC On Boot: Enabled.

The equivalent compile FQBN is recorded in `project-meta.json`.

## Expected result

Serial Monitor at 115200 baud reports startup and a five-second heartbeat. The
display shows **Waveshare 4.3B is ready**, a pause button, current pause and
click state, a sine-speed slider, and a 0-100 sine output gauge. Button taps
toggle the pause command. Slider movement updates the speed command and touch
coordinates. Values sent from Visuino move the gauge needle and numeric label.

Compilation proves the complete source and dependency set. Final electrical
verification still requires uploading to the physical 4.3B board and touching
the screen.
