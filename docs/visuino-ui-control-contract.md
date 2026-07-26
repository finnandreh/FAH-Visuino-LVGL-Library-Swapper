# Visuino UI Control Contract

## Interpreted Intent

The Waveshare 4.3B screen must be more than a local touch demonstration. Every
interactive control must expose a stable bridge that Visuino Custom Code can
read or write without reaching into private LVGL implementation details.

The first complete demonstration uses:

- a 0-100 slider as a sine-wave speed command from the screen to Visuino;
- a pause button as a Boolean pause command and click event from the screen to
  Visuino;
- a 0-100 gauge as the sine-wave value display from Visuino to the screen.

Success means the bridge can be called from parsed Visuino Custom Code, the UI
remains responsive, and all LVGL access is protected by the existing LVGL
mutex.

## Confirmed Requirements

- Every button must expose at least a readable state or one-shot event API.
- Every slider must expose its current value and a write API.
- Output-only indicators such as gauges must expose a write API.
- `waveshare43_example::set_test_slider_value(AValue);` is the approved
  Visuino Input-field form for moving the slider.
- `waveshare43_example` is the required C++ bridge namespace. Operators must
  keep `waveshare43_example::` before every project bridge function name.
- Visuino owns the sine-wave generator and its component wiring.
- The UI bridge must make all required values available to that Visuino logic.

## Assumptions

- The existing integer Custom Code input uses `int32_t AValue`.
- The slider and gauge use the inclusive range 0-100.
- A practical initial Visuino mapping is slider 0-100 to a user-selected sine
  frequency range. The firmware does not force a frequency formula.
- `pause = true` means the Visuino sine-wave flow should stop. If a Visuino
  component expects `Enabled`, use the inverse value.

## System Classification And Scope

This is a display-and-touch node with a manual UI-to-Visuino bridge.

In scope:

- LVGL slider, pause button, and gauge;
- stable thread-safe read/write/event functions;
- `ui-elements.json` entries and operator examples;
- source package, active test profile, and application help text.

Out of scope:

- generating the sine wave inside the display library;
- automatic Visuino component creation or wiring;
- vehicle, CAN, RS485, or external actuator control.

## Execution And State Model

The existing cooperative Arduino loop remains the smallest valid execution
model. LVGL continues to run through `waveshare43_example::loop()`. Bridge calls
lock the LVGL mutex before reading or changing widgets.

The UI state model is:

1. `running`: pause is false and the pause button invites the operator to pause;
2. `paused`: pause is true and the button invites the operator to resume;
3. slider changes: publish a one-shot changed flag and retain the current
   0-100 speed value;
4. gauge updates: retain and display the latest 0-100 value received from
   Visuino.

The pause state is a command for Visuino. It does not independently suspend a
generator inside the display library.

## Stable Bridge API

All functions in this table belong to `waveshare43_example`. The short names
make the table easier to scan, but the complete call used in Visuino must use:

```cpp
waveshare43_example::function_name(...);
```

The `::` tells C++ to find the function inside the
`waveshare43_example` namespace. It is required; it is not decorative. Global
LVGL functions beginning with `lv_` do not use this project namespace.

| UI element | Direction | Stable API |
|---|---|---|
| Pause button | UI to Visuino | `take_touch_button_click()`, `get_pause_state()`, `take_pause_state_change()` |
| Pause button | Visuino to UI | `set_pause_state(value)` |
| Speed slider | UI to Visuino | `get_test_slider_value()`, `take_test_slider_change()` |
| Speed slider | Visuino to UI | `set_test_slider_value(value)` |
| Sine gauge | Visuino to UI | `set_sine_gauge_value(value)` |
| Sine gauge | Readback | `get_sine_gauge_value()` |

All setters return `bool` to report whether the screen was ready and the update
was accepted. Values are clamped to 0-100.

## Safety And Failover

- UI bridge calls return `false` or zero-compatible defaults before the screen
  is ready or when the LVGL lock cannot be acquired.
- No bridge call controls physical power, backlight PWM, or an external
  actuator.
- A missed one-shot flag does not corrupt the retained pause or slider value;
  Visuino can always read the current state again.
- Physical validation still requires upload and touch testing on the exact
  Waveshare 4.3B board.

## Visuino Examples

Move the slider from an Integer Input field:

```cpp
waveshare43_example::set_test_slider_value(AValue);
```

`AValue` is the value received by that Visuino Input. Copy the complete line,
including `waveshare43_example::` and the final semicolon.

Read the slider in the Custom Code loop:

```cpp
if (waveshare43_example::take_test_slider_change()) {
  Integer1.Send(waveshare43_example::get_test_slider_value());
}
```

Send the pause state:

```cpp
if (waveshare43_example::take_pause_state_change()) {
  Digital1.Send(waveshare43_example::get_pause_state());
}
```

Send an enable state instead:

```cpp
Digital1.Send(!waveshare43_example::get_pause_state());
```

Move the gauge from a sine-wave Integer Input field:

```cpp
waveshare43_example::set_sine_gauge_value(AValue);
```

Use this setter once. It clamps the input to 0-100 and updates the meter needle,
the percentage label, and the retained readback value together. The percentage
label does not require a second Visuino Input.

A complete working loop is:

```cpp
waveshare43_example::loop();

if (waveshare43_example::take_test_slider_change()) {
  Integer1.Send(waveshare43_example::get_test_slider_value());
}

if (waveshare43_example::take_pause_state_change()) {
  Digital1.Send(waveshare43_example::get_pause_state());
}
```

## Artifact Mapping And Validation

- Product behavior and safety: `docs/system-spec.md`
- Project Vault behavior: `docs/project-vault.md`
- Reference-device contract: `docs/waveshare-4.3b-firmware-spec.md`
- Public API and UI: `source-import/Waveshare-4.3B-Example/`
- Manual binding registry: `source-import/Waveshare-4.3B-Example/ui-elements.json`

Validation requires JSON parsing, project tests, an ESP32-S3 compile, and a
physical slider/button/gauge interaction test. Future widgets follow the same
minimum contract: inputs expose values/events, indicators expose setters, and
bidirectional widgets expose both.
