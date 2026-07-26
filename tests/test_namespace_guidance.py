"""Namespace guidance presentation tests."""

import unittest

from lvgl_visuino_setup_manager.custom_code_dialog import (
    format_ui_element_details,
)
from lvgl_visuino_setup_manager.implementation import UiElementVariable


class NamespaceGuidanceTests(unittest.TestCase):
    def test_bridge_namespace_and_exact_visuino_examples_are_explicit(self) -> None:
        element = UiElementVariable(
            id="test_slider",
            name="Sine speed slider",
            screen="Hardware Test",
            type="slider",
            lvgl_object="ui_test_slider",
            direction="bidirectional",
            value_type="int",
            description="Speed control.",
            read_api="waveshare43_example::get_test_slider_value()",
            write_api="waveshare43_example::set_test_slider_value(value)",
            bridge_namespace="waveshare43_example",
            visuino_input_code=(
                "waveshare43_example::set_test_slider_value(AValue);"
            ),
            visuino_loop_code=(
                "Integer1.Send("
                "waveshare43_example::get_test_slider_value());"
            ),
        )

        details = format_ui_element_details(element)

        self.assertIn("Namespace:      waveshare43_example", details)
        self.assertIn("do not remove it", details)
        self.assertIn(
            "waveshare43_example::set_test_slider_value(AValue);",
            details,
        )
        self.assertIn(
            "Integer1.Send("
            "waveshare43_example::get_test_slider_value());",
            details,
        )

    def test_legacy_element_explains_missing_namespace(self) -> None:
        element = UiElementVariable(
            id="legacy_label",
            name="Legacy label",
            screen="Main",
            type="label",
            lvgl_object="ui_legacy_label",
            direction="custom_code_to_ui",
            value_type="string",
            description="Legacy entry.",
            read_api="lv_label_get_text(ui_legacy_label)",
        )

        details = format_ui_element_details(element)

        self.assertIn("not declared by this legacy import", details)
        self.assertIn("Global LVGL functions beginning with lv_", details)


if __name__ == "__main__":
    unittest.main()
