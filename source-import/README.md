# Source Import

Place standalone Arduino/LVGL implementations in separate subfolders here.
Each selectable import folder must contain:

- exactly one `.ino` file at the folder root;
- all related LVGL headers, sources, UI files, assets, configuration, and
  optional project-specific libraries below that same folder.
- `ui-elements.json` at the folder root for every new GPT-generated project,
  documenting variable widgets and their exact LVGL object names.

An import with no root `.ino`, or with more than one root `.ino`, is rejected.
The application never guesses which sketch to use and never generates a
replacement during source import.

Each valid subfolder can be selected directly in:

1. Open **Device & Custom Code**.
2. Select **Standalone Import**.
3. Choose the desired source subfolder.
4. Choose **Analyze & Import**.

The application reads the selected source folder. It does not execute or modify
the source files. After import, the LVGL project files are routed into the
selected setup and the one root `.ino` is shown by itself on **Visuino Custom
Code**, ready for **Copy to Clipboard**. In Visuino, add a Custom Code component,
open its Arduino Code Import/Parser, paste the complete INO into the importer,
and choose Parse. Visuino then separates includes/globals, `setup()`, and
`loop()` into the correct component sections. Do not paste the whole sketch as
raw code into one method field.

When `ui-elements.json` is present, the application validates it, stores it
with the imported implementation, and lists its buttons, sliders, labels, and
other variables under **UI Element Variables**. Older manual folders without
the document still import with an empty list and a dry-run warning.

Use **Device & Custom Code → Shared GPT** to open the published LVGL Library
Swapper assistant. Describe the display and desired UI, request the complete
import ZIP, choose Extract All, and select the extracted top-level project
folder under **Standalone Import**. The desktop application does not display or
copy the authoritative GPT prompt.

`Waveshare-4.3B-Example` is the complete compile-tested package for the exact
Waveshare ESP32-S3-Touch-LCD-4.3B. It includes LVGL 8.4.0, the ST7262 RGB
display driver, GT911 touch, CH422G expansion and backlight support, and a
visible pause, sine-speed slider, and sine-gauge UI with a stable Visuino bridge.
The underlying LCD, backlight, touch, button, and slider path has been physically
verified. Any changed device or UI revision must still repeat compilation,
upload, and physical interaction testing.
