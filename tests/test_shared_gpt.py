from __future__ import annotations

import inspect
import unittest

from lvgl_visuino_setup_manager.custom_code_dialog import CustomCodeDialog
from lvgl_visuino_setup_manager.shared_gpt import (
    SHARED_GPT_INSTRUCTIONS,
    SHARED_GPT_KNOWLEDGE_VERSION,
    SHARED_GPT_NAME,
    SHARED_GPT_START_STEPS,
    SHARED_GPT_URL,
    validate_shared_gpt_url,
)


class SharedGptTests(unittest.TestCase):
    def test_owner_instructions_match_the_current_knowledge_contract(self) -> None:
        self.assertEqual(SHARED_GPT_KNOWLEDGE_VERSION, "2026-07-25.1")

        expected = (
            "lvgl-library-swapper-gpt-prompt.md",
            "PROMPT_VERSION is 2026-07-25.1",
            "Remove Profile, Clear Folder Contents, and Delete Profile and Folder",
            "180-second cache guidance",
            "waveshare43_example:: slider, pause, and gauge examples",
            "single gauge setter",
            "Never claim that a ZIP, compile, upload, import, activation, or "
            "physical hardware test occurred",
        )
        for phrase in expected:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, SHARED_GPT_INSTRUCTIONS)

    def test_published_link_is_exact_and_safely_scoped(self) -> None:
        self.assertEqual(SHARED_GPT_NAME, "LVGL Library Swapper")
        self.assertEqual(
            SHARED_GPT_URL,
            "https://chatgpt.com/g/"
            "g-6a63a706c35081918edae0ce7a6096f2-lvgl-library-swapper",
        )
        self.assertEqual(validate_shared_gpt_url(), SHARED_GPT_URL)

    def test_url_validation_rejects_unapproved_variants(self) -> None:
        for value in (
            "",
            "http://chatgpt.com/g/g-example",
            "https://example.com/g/g-example",
            "https://user:secret@chatgpt.com/g/g-example",
            "https://chatgpt.com/c/example",
            "https://chatgpt.com/g/g-example?source=desktop",
            "https://chatgpt.com/g/g-example#fragment",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_shared_gpt_url(value)

    def test_getting_started_covers_the_complete_handoff(self) -> None:
        combined = " ".join(
            f"{title} {detail}" for title, detail in SHARED_GPT_START_STEPS
        )
        self.assertEqual(len(SHARED_GPT_START_STEPS), 4)
        self.assertIn("display", combined)
        self.assertIn("ZIP", combined)
        self.assertIn("Extract All", combined)
        self.assertIn("top-level project folder", combined)
        self.assertIn("Analyze & Import", combined)

    def test_desktop_dialog_has_no_editable_prompt_controls(self) -> None:
        source = inspect.getsource(CustomCodeDialog)

        self.assertIn("Open Shared GPT", source)
        self.assertIn("Copy Link", source)
        self.assertFalse(hasattr(CustomCodeDialog, "_reset_meta_prompt"))
        self.assertFalse(hasattr(CustomCodeDialog, "_copy_meta_prompt"))
        self.assertFalse(hasattr(CustomCodeDialog, "_export_website_prompt"))
        self.assertFalse(hasattr(CustomCodeDialog, "_copy_website_launcher"))
        self.assertNotIn("Reset Meta Prompt", source)
        self.assertNotIn("Copy Meta Prompt", source)
        self.assertNotIn("Copy Short Launcher", source)


if __name__ == "__main__":
    unittest.main()
