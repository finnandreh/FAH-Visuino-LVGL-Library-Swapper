# Waveshare 4.3B Standalone Firmware Specification

## Target

The implementation targets the exact Waveshare
`ESP32-S3-Touch-LCD-4.3B` board with an ESP32-S3-WROOM-1-N16R8 module. It is
not a generic 4.3-inch display package.

The board contract is:

- 800 x 480 ST7262 panel over a 16-bit RGB bus;
- GT911 five-point capacitive touch over I2C on GPIO8/GPIO9 with IRQ on GPIO4;
- CH422G I/O expander at I2C address `0x20`;
- touch reset on CH422G EXIO1;
- display/backlight enable on CH422G EXIO2;
- 16 MB flash and 8 MB OPI PSRAM.

## Runtime

`waveshare43_example::begin()` creates and validates all four hardware driver
objects, executes the board-specific reset sequence, starts the LCD, touch and
backlight, registers the LVGL display and input devices, and creates the visible
hardware-test screen.

`waveshare43_example::loop()` drives `lv_timer_handler()` under the LVGL
recursive mutex and emits a serial heartbeat every five seconds.

Any startup failure is reported at 115200 baud and leaves the firmware in an
idle loop. The UI is not created unless LCD, touch, expander, backlight, and
LVGL registration have all succeeded.

## Visible acceptance result

The screen must show:

- `Waveshare 4.3B is ready`;
- ST7262, GT911, CH422G, LVGL, and runtime status;
- a large pause/resume button whose color, retained state, and counter change on
  every tap;
- the last touch coordinates;
- a 0-100 sine-speed slider whose visible percentage changes while it is
  dragged;
- a 0-100 speedometer-style sine gauge with a numeric percentage label.

The slider validates continuous touch. It does not control brightness because
this board exposes the backlight through an on/off CH422G output rather than a
PWM channel.

The slider and pause state travel from LVGL to Visuino through
namespace-qualified bridge functions. Visuino generates the 0-100 sine value
and sends it back through one gauge setter. That setter updates the needle and
percentage label together.

## Build acceptance

The root INO must compile after the folder is imported by
FAH Visuino LVGL Library Swapper
into an otherwise isolated setup. The compile target is ESP32 Arduino core
3.3.10, ESP32S3 Dev Module, 16 MB QIO flash, OPI PSRAM, and a 3 MB application
partition.

Compilation is necessary but not sufficient for final acceptance. LCD timing,
touch coordinates, and backlight operation must also be confirmed by uploading
the binary to the physical 4.3B board. A changed UI bridge revision must repeat
the slider, pause, and gauge interaction test even when the underlying hardware
drivers were already verified.
