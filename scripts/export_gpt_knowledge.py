from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from lvgl_visuino_setup_manager.meta_prompt import (  # noqa: E402
    GPT_PROJECT_META_PROMPT,
    GPT_PROJECT_PROMPT_VERSION,
)


DEFAULT_DESTINATION = (
    PROJECT_ROOT
    / "gpt-knowledge"
    / "lvgl-library-swapper-gpt-prompt.md"
)


def main() -> int:
    destination = (
        Path(sys.argv[1]).expanduser().resolve()
        if len(sys.argv) > 1
        else DEFAULT_DESTINATION
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        GPT_PROJECT_META_PROMPT,
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"Exported GPT Knowledge version {GPT_PROJECT_PROMPT_VERSION}: "
        f"{destination}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
