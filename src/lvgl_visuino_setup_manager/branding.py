from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageTk


HEADER_DEDICATION = "DEDICATED TO VISUINO"
DEVELOPER_NAME = "Finn Andre Hotvedt"
DEVELOPER_LINE = f"Developed by {DEVELOPER_NAME}"

VISUINO_URL = "https://www.visuino.com/"
FINNANDRE_URL = "https://finnandre.no/"

DEDICATION_PARAGRAPHS = (
    (
        "FAH Visuino LVGL Library Swapper is dedicated to Visuino and to the "
        "work of its creator, Boian Mitov. Visuino is an exceptional visual "
        "development environment built through years of focused work and "
        "dedication."
    ),
    (
        "FAH Visuino LVGL Library Swapper was developed to make Arduino "
        "library environments easier to organize, isolate, and "
        "reproduce—especially for businesses that need dependable library "
        "sets for individual customers, products, and projects."
    ),
    (
        "Controlled library management is also an important technical "
        "foundation for dependable LVGL support in Visuino. By making "
        "versions, configurations, and project-specific dependencies easier "
        "to manage, FAH Visuino LVGL Library Swapper is intended to help that "
        "support move forward more safely and efficiently."
    ),
    (
        "Special thanks to Ron Cutts for the extensive time contributed to "
        "testing and design."
    ),
)

RECOGNITION_LINES = (
    "Boian Mitov — Creator of Visuino",
    "Ron Cutts — Contributor: testing and design",
)

ATTRIBUTION_LINES = (
    *RECOGNITION_LINES,
    DEVELOPER_LINE,
)

INDEPENDENCE_STATEMENT = (
    "FAH Visuino LVGL Library Swapper is an independently developed tool "
    "dedicated to Visuino. It is not presented as an official Visuino product "
    "unless separately approved by the Visuino organization."
)


def resource_path(relative_path: str | Path) -> Path:
    """Resolve a bundled resource in source and PyInstaller builds."""
    relative = Path(relative_path)
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return (Path(bundle_root) / relative).resolve(strict=False)
    return (Path(__file__).resolve().parents[2] / relative).resolve(strict=False)


def finnandre_logo_path() -> Path:
    return resource_path(Path("assets") / "branding" / "finnandre-logo.png")


def load_finnandre_logo(
    size: int,
    *,
    master: object | None = None,
) -> ImageTk.PhotoImage:
    """Load the logo at an exact, antialiased display size."""
    if size <= 0:
        raise ValueError("Logo size must be positive.")
    with Image.open(finnandre_logo_path()) as source:
        logo = source.convert("RGBA")
        visible_bounds = logo.getbbox()
        if visible_bounds is not None:
            logo = logo.crop(visible_bounds)
        logo = logo.resize(
            (size, size),
            Image.Resampling.LANCZOS,
            reducing_gap=3.0,
        )
    return ImageTk.PhotoImage(logo, master=master)
