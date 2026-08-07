"""LiteParse adapter for fast local born-digital PDF parsing."""
from __future__ import annotations

from pathlib import Path

from parsers.base import BaseParser


class LiteParseParser(BaseParser):
    """Spatial PDFium parsing with local Markdown and image references."""

    name = "liteparse"

    def __init__(self) -> None:
        # LiteParse exposes structured page results in addition to the combined
        # Markdown.  Keep a lightweight page-indexed text view for the UI and
        # provenance checks; Markdown remains the parser interchange format.
        self.last_page_text: dict[int, str] = {}

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
        self.last_page_text = self._collect_page_text(result)
        markdown = (result.text or "").strip()
        if not markdown:
            raise RuntimeError("LiteParse returned empty Markdown")
        return markdown

    @staticmethod
    def _collect_page_text(result: object) -> dict[int, str]:
        """Read LiteParse's optional per-page items without coupling to a version.

        Different LiteParse releases expose item text as attributes or dict
        fields.  This deliberately degrades to an empty mapping: it must never
        make a valid Markdown parse fail merely because page metadata changed.
        """
        page_text: dict[int, str] = {}
        for fallback_number, page in enumerate(getattr(result, "pages", []) or [], 1):
            page_number = getattr(page, "page_num", getattr(page, "page_number", fallback_number))
            try:
                page_number = int(page_number)
            except (TypeError, ValueError):
                page_number = fallback_number

            items = getattr(page, "text_items", None) or getattr(page, "items", None) or []
            texts: list[str] = []
            for item in items:
                text = item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
                if str(text).strip():
                    texts.append(str(text).strip())
            if texts:
                page_text[page_number] = "\n\n".join(texts)
        return page_text
