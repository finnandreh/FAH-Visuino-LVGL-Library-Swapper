# Third-Party Notices

FAH Visuino LVGL Library Swapper is licensed under Apache License 2.0 for
original project code and documentation. Bundled and runtime third-party
components remain under their own licenses.

## Bundled Arduino and LVGL components

| Component | Version | License | Upstream | Bundled license |
|---|---:|---|---|---|
| LVGL | 8.4.0 | MIT | <https://github.com/lvgl/lvgl> | `source-import/Waveshare-4.3B-Example/libraries/lvgl/LICENCE.txt` |
| ESP32_Display_Panel | 1.0.0 | Apache-2.0, with CC0-1.0 example/port files where marked | <https://github.com/esp-arduino-libs/ESP32_Display_Panel> | `source-import/Waveshare-4.3B-Example/libraries/ESP32_Display_Panel/license.txt` |
| ESP32_IO_Expander | 1.0.1 | Apache-2.0 | <https://github.com/esp-arduino-libs/ESP32_IO_Expander> | `source-import/Waveshare-4.3B-Example/libraries/ESP32_IO_Expander/license.txt` |
| esp-lib-utils | 0.1.2 | Apache-2.0, with CC0-1.0 example files where marked | <https://github.com/esp-arduino-libs/esp-lib-utils> | `source-import/Waveshare-4.3B-Example/libraries/esp-lib-utils/license.txt` |

The two standalone LVGL port files below retain Espressif copyright and
CC0-1.0 SPDX declarations:

- `source-import/Waveshare-4.3B-Example/include/lvgl_v8_port.h`
- `source-import/Waveshare-4.3B-Example/src/lvgl_v8_port.cpp`

The vendored LVGL distribution also contains upstream fonts, image assets,
utilities, and embedded helper code with notices retained in their source
files. Those file-level notices continue to apply.

## Python runtime and build components

These packages are resolved from the Python environment and are not vendored as
source in this repository:

| Component | Role | License |
|---|---|---|
| Pillow | Runtime image support | HPND |
| Send2Trash | Recoverable Windows Recycle Bin operations | BSD-3-Clause |
| PyInstaller | Windows packaging tool | GPL-2.0-or-later with the PyInstaller bootloader exception |

The PyInstaller bootloader exception permits distributing executables that
embed the bootloader without applying GPL restrictions to the bundled
application. PyInstaller's own files remain governed by its upstream terms.

## Trademarks

Visuino, Arduino, LVGL, Espressif, Waveshare, and other product names are used
only to identify compatibility and origin. Their trademarks remain with their
respective owners. FAH Visuino LVGL Library Swapper is independently developed
and is not represented as an official product of those projects or companies.

When redistributing the repository or release package, retain the root
`LICENSE`, `NOTICE`, this file, and the license notices stored with bundled
third-party components.
