"""LiteParse adapter for fast local born-digital PDF parsing."""
from __future__ import annotations

from pathlib import Path

from parsers.base import BaseParser


class LiteParseParser(BaseParser):
    """Spatial PDFium parsing with local Markdown and image references."""

    name = "liteparse"

    def parse(self, file_path: str) -> str:
        try:
            from liteparse import LiteParse
        except ImportError as exc:
            raise RuntimeError("LiteParse is not installed. Run: pip install liteparse") from exc

        image_dir = Path("artifacts") / "liteparse_images" / Path(file_path).stem
        image_dir.mkdir(parents=True, exist_ok=True)
        parser = LiteParse(
            output_format="markdown",
            ocr_enabled=False,
            image_mode="placeholder",
            extract_images=True,
            image_output_dir=str(image_dir),
            extract_links=True,
            quiet=True,
        )
        result = parser.parse(file_path)
        markdown = (result.text or "").strip()
        if not markdown:
            raise RuntimeError("LiteParse returned empty Markdown")
        return markdown
