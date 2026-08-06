"""
ParserRouter — content-based language detection and document routing.

Features:
  - Content-based language detection via character frequency and langdetect.
  - Primary Local Engine: DoclingParser (free, offline, layout-aware).
  - Scanned Document Engine: TesseractParser (free, offline OCR).
  - Emergency Fallback Engine: LlamaParser (LlamaCloud API, credit-conserving fallback).
"""
from __future__ import annotations

import re
import fitz
from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

from parsers.base import BaseParser
from parsers.docling_parser import DoclingParser
from parsers.llama_parser import LlamaParser
from parsers.ocr_parser import TesseractParser
from routing.probe import probe_document, ProbeResult

DetectorFactory.seed = 0


def detect_language_from_content(file_path: str, sample_pages: int = 5) -> str:
    """Detect primary document language from actual text content.

    Args:
        file_path: Path to the input document.
        sample_pages: Number of initial pages to sample.

    Returns:
        ``ar``, ``en``, ``mixed``, or ``unknown`` based only on PDF text.
    """
    try:
        doc = fitz.open(file_path)
        sampled_text = []

        for i in range(min(sample_pages, len(doc))):
            text = doc[i].get_text().strip()
            if text:
                sampled_text.append(text)
        doc.close()

        if not sampled_text:
            return _detect_language_with_osd(file_path)

        full_text = " ".join(sampled_text)
        arabic_char_count = sum(1 for c in full_text if "\u0600" <= c <= "\u06FF")
        latin_char_count = sum(1 for c in full_text if c.isascii() and c.isalpha())
        total_char_count = max(len(full_text.strip()), 1)

        # Character frequency heuristic
        arabic_ratio = arabic_char_count / total_char_count
        latin_ratio = latin_char_count / total_char_count
        if arabic_ratio > 0.15 and latin_ratio > 0.15:
            return "mixed"
        if arabic_ratio > 0.15:
            return "ar"

        # Statistical detection
        clean_text = re.sub(r"[0-9\s\.\,\;\:\-\(\)\[\]\{\}]+", " ", full_text).strip()
        if len(clean_text) > 50:
            detected = detect(clean_text[:1000])
            if detected.startswith("ar"):
                return "ar"

        return "en" if latin_char_count else "unknown"
    except (LangDetectException, Exception):
        return _detect_language_with_osd(file_path)


def _detect_language_with_osd(file_path: str, sample_pages: int = 10) -> str:
    """Use Tesseract OSD for scans only, rejecting low-confidence cover pages."""
    try:
        import io
        from PIL import Image
        import pytesseract

        document = fitz.open(file_path)
        try:
            for page in document[:sample_pages]:
                pixmap = page.get_pixmap(dpi=150, alpha=False)
                image = Image.open(io.BytesIO(pixmap.tobytes("png")))
                osd = pytesseract.image_to_osd(image)
                confidence_match = re.search(r"Script confidence:\s*([\d.]+)", osd, re.IGNORECASE)
                script_match = re.search(r"Script:\s*(\w+)", osd, re.IGNORECASE)
                confidence = float(confidence_match.group(1)) if confidence_match else 0.0
                script = script_match.group(1).lower() if script_match else ""
                if confidence < 10:
                    continue
                if script == "arabic":
                    return "ar"
                if script in {"latin", "cyrillic"}:
                    return "en"
        finally:
            document.close()
    except Exception:
        pass
    return "unknown"


class ParserRouter:
    """Document router that selects local parsers first and reserves cloud APIs for fallbacks."""

    def __init__(self) -> None:
        self._registry: dict[str, BaseParser] = {
            "docling": DoclingParser(),
            "tesseract": TesseractParser(lang="ara+eng"),
            "ocr_parser": TesseractParser(lang="ara+eng"),
            "llamaparse": LlamaParser(language="auto"),
        }
        self._llama_cache: dict[str, LlamaParser] = {}

    def get_llama_parser(self, language: str) -> LlamaParser:
        """Retrieve or instantiate a LlamaParser configured for the specified language."""
        if language not in self._llama_cache:
            self._llama_cache[language] = LlamaParser(language=language)
        return self._llama_cache[language]

    def select(self, probe: ProbeResult, file_path: str | None = None) -> BaseParser:
        """Select the optimal parser for the given document.

        Priority:
          1. Non-born-digital / scanned -> Tesseract OCR
          2. Born-digital (standard & complex) -> DoclingParser (local & free)
          3. Emergency Fallback -> LlamaParser (API credit preservation)
        """
        if not probe.is_born_digital:
            return self._registry.get("ocr_parser", self._registry.get("tesseract"))

        return self._registry["docling"]

    def build_chain(self, probe: ProbeResult, language: str) -> list[BaseParser]:
        """Build an ordered, content-driven parser fallback chain.

        Born-digital PDFs retain their text layer, so Docling is the preferred
        layout-aware parser.  Scanned PDFs have no usable text layer; running
        Docling first only consumes RAM, therefore local Tesseract starts the
        scan path and LlamaParse remains the cloud recovery option.
        """
        ocr_language = {"ar": "ara", "en": "eng"}.get(language, "ara+eng")
        llama_language = language if language in {"ar", "en"} else "auto"
        if probe.is_born_digital:
            return [
                self._registry["docling"],
                self.get_llama_parser(llama_language),
                TesseractParser(lang=ocr_language),
            ]
        return [
            TesseractParser(lang=ocr_language),
            self.get_llama_parser(llama_language),
        ]

    def route(self, file_path: str) -> tuple[BaseParser, ProbeResult, str]:
        """Probe document, detect content language, and return (selected_parser, probe, detected_language)."""
        probe = probe_document(file_path)
        detected_lang = detect_language_from_content(file_path)
        parser = self.select(probe, file_path)
        return parser, probe, detected_lang
