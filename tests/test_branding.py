from __future__ import annotations

import unittest

from lvgl_visuino_setup_manager import APP_NAME, __version__
from lvgl_visuino_setup_manager.branding import (
    ATTRIBUTION_LINES,
    DEDICATION_PARAGRAPHS,
    DEVELOPER_LINE,
    FINNANDRE_URL,
    HEADER_DEDICATION,
    INDEPENDENCE_STATEMENT,
    VISUINO_URL,
    finnandre_logo_path,
)


class BrandingTests(unittest.TestCase):
    def test_public_product_name_uses_the_fah_prefix(self) -> None:
        self.assertEqual("FAH Visuino LVGL Library Swapper", APP_NAME)

    def test_approved_dedication_and_attribution_are_present(self) -> None:
        complete_copy = "\n".join(
            (*DEDICATION_PARAGRAPHS, *ATTRIBUTION_LINES, INDEPENDENCE_STATEMENT)
        )

        self.assertEqual("DEDICATED TO VISUINO", HEADER_DEDICATION)
        self.assertIn("Boian Mitov", complete_copy)
        self.assertIn("Ron Cutts", complete_copy)
        self.assertIn("testing and design", complete_copy)
        self.assertIn("businesses", complete_copy)
        self.assertIn("dependable LVGL support in Visuino", complete_copy)
        self.assertEqual("Developed by Finn Andre Hotvedt", DEVELOPER_LINE)
        self.assertIn("independently developed", INDEPENDENCE_STATEMENT)

    def test_branding_assets_and_links_are_local_and_explicit(self) -> None:
        logo = finnandre_logo_path()

        self.assertTrue(logo.is_file())
        self.assertEqual(b"\x89PNG\r\n\x1a\n", logo.read_bytes()[:8])
        self.assertEqual("https://www.visuino.com/", VISUINO_URL)
        self.assertEqual("https://finnandre.no/", FINNANDRE_URL)

    def test_release_version_is_one_point_zero_point_one(self) -> None:
        self.assertEqual("1.0.1", __version__)


if __name__ == "__main__":
    unittest.main()
