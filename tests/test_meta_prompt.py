from __future__ import annotations

import unittest
from pathlib import Path

from lvgl_visuino_setup_manager.meta_prompt import (
    GPT_PROJECT_META_PROMPT,
    GPT_PROJECT_PROMPT_VERSION,
)


class MetaPromptTests(unittest.TestCase):
    def test_prompt_version_matches_the_complete_v1_0_1_help_update(self) -> None:
        self.assertEqual(GPT_PROJECT_PROMPT_VERSION, "2026-07-25.1")

    def test_prompt_locks_the_two_phase_strict_import_contract(self) -> None:
        prompt = GPT_PROJECT_META_PROMPT

        self.assertTrue(
            prompt.startswith(
                "FAH VISUINO LVGL LIBRARY SWAPPER — GPT GUIDE AND PROJECT GENERATOR"
            )
        )
        self.assertIn("must remain written and displayed in English", prompt)
        self.assertIn(
            f"PROMPT_VERSION: {GPT_PROJECT_PROMPT_VERSION}",
            prompt,
        )
        self.assertIn("BEGIN AUTHORITATIVE INSTRUCTIONS", prompt)
        self.assertIn("END AUTHORITATIVE INSTRUCTIONS", prompt)
        self.assertIn("YOUR MAIN PURPOSE", prompt)
        self.assertIn("what every main concept and command", prompt)
        self.assertIn("SMART ONBOARDING BEHAVIOR", prompt)
        self.assertIn("not a static questionnaire", prompt)
        self.assertIn("one to three questions", prompt)
        self.assertIn("Reuse every detail", prompt)
        self.assertIn("Confirmed information", prompt)
        self.assertIn("Recommended next step", prompt)
        self.assertIn("small first milestone", prompt)
        self.assertIn("what is ready, what is still", prompt)
        self.assertIn("DELIVERY MODE", prompt)
        self.assertIn("Local workspace mode", prompt)
        self.assertIn("Chat ZIP mode", prompt)
        self.assertIn(
            "Would you like me to deliver the completed import folder as",
            prompt,
        )
        self.assertIn("exactly one top-level", prompt)
        self.assertIn("ZIP ARCHIVE MANIFEST", prompt)
        self.assertIn("<ProjectName>/libraries/<ArduinoLibraryName>/...", prompt)
        self.assertIn("Do not create\n`libraries/libraries/`", prompt)
        self.assertIn("no path contains `..`", prompt)
        self.assertIn("`__MACOSX`", prompt)
        self.assertIn("choose Extract All", prompt)
        self.assertIn("Do not select the ZIP file", prompt)
        self.assertIn(
            "Never claim that a local folder or ZIP was created",
            prompt,
        )
        self.assertIn("Client: the customer or owner grouping", prompt)
        self.assertIn("Validate Setup:", prompt)
        self.assertIn("Standalone Import:", prompt)
        self.assertIn("UI Element Variables:", prompt)
        self.assertIn('"bridgeNamespace": "<valid_cpp_namespace>"', prompt)
        self.assertIn(
            '"visuinoInputCode": "<namespace>::set_value(AValue);"',
            prompt,
        )
        self.assertIn(
            "must not be removed",
            prompt,
        )
        self.assertIn("PROJECT CREATION MODE", prompt)
        self.assertIn("build LVGL for a specific screen", prompt)
        self.assertIn(
            "do not ask the entire list in one",
            prompt,
        )
        self.assertIn("PHASE 1", prompt)
        self.assertIn("PHASE 2", prompt)
        self.assertIn("create a real folder", prompt)
        self.assertIn("after any ZIP is extracted", prompt)
        self.assertIn("exactly one .ino file at the folder root", prompt)
        self.assertIn("Do not create any other .ino file", prompt)
        self.assertIn("Visuino Custom Code component", prompt)
        self.assertIn("ui-elements.json", prompt)
        self.assertIn("Every button must expose", prompt)
        self.assertIn("Every slider must expose", prompt)
        self.assertIn("Custom Code-driven indicator", prompt)
        self.assertIn("lvglObject", prompt)
        self.assertIn("ui_to_custom_code", prompt)
        self.assertIn("later manual Custom Code linking", prompt)
        self.assertIn("setup()", prompt)
        self.assertIn("loop()", prompt)
        self.assertIn("USAGE HELP MODE", prompt)
        self.assertIn("Arduino Code Import/Parser", prompt)
        self.assertIn("run Parse", prompt)
        self.assertIn(
            "Do not paste the whole .ino as raw code into one method",
            prompt,
        )
        self.assertIn(
            "setup() becomes the component initialization",
            prompt,
        )
        self.assertIn(
            "Do not require GPT to compile the project",
            prompt,
        )
        self.assertIn("attach the downloadable", prompt)

    def test_prompt_covers_the_complete_released_support_surface(self) -> None:
        prompt = GPT_PROJECT_META_PROMPT

        expected_sections = (
            "CURRENT PRODUCT IDENTITY AND REFERENCE RELEASE",
            "PROFILE MANAGEMENT AND RECOVERABLE CLEANUP",
            "VALIDATION PRESENTATION AND BASELINE HELP",
            "ACTIVATION AND CACHE TROUBLESHOOTING",
            "WAVESHARE 4.3B REFERENCE BRIDGE",
            "COMMON SUPPORT ANSWERS",
        )
        for section in expected_sections:
            with self.subTest(section=section):
                self.assertIn(section, prompt)

        expected_facts = (
            "FAH-Waveshare43-Demo-Package-2026-07-25.zip",
            "Boian Mitov",
            "Ron Cutts",
            "Clear Folder Contents",
            "Delete Profile and Folder",
            "Windows Recycle Bin",
            "DELETE <profile name>",
            "fixed 180-second cache-verification deadline",
            "waveshare43_example::set_test_slider_value(AValue);",
            "waveshare43_example::take_test_slider_change()",
            "waveshare43_example::take_pause_state_change()",
            "waveshare43_example::set_sine_gauge_value(AValue);",
            "gauge needle,\npercentage label, and retained readback value",
            "Do not create a second\nVisuino Input for the percentage label",
        )
        for fact in expected_facts:
            with self.subTest(fact=fact):
                self.assertIn(fact, prompt)

    def test_deployment_knowledge_file_matches_the_authoritative_source(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        knowledge_file = (
            project_root
            / "gpt-knowledge"
            / "lvgl-library-swapper-gpt-prompt.md"
        )

        self.assertTrue(knowledge_file.is_file())
        self.assertEqual(
            knowledge_file.read_text(encoding="utf-8"),
            GPT_PROJECT_META_PROMPT,
        )

if __name__ == "__main__":
    unittest.main()
