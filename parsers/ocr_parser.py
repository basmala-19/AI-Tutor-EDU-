"""
Tesseract OCR Parser — supports Arabic ('ara'), English ('eng'), and mixed document OCR.

Requires Tesseract binary installed on the OS:
  - Windows: https://github.com/UB-Mannheim/tesseract/wiki
  - Linux:   sudo apt install tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng
  - Mac:     brew install tesseract tesseract-lang
"""
from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Optional

import fitz
from PIL import Image
import pytesseract
from pytesseract import Output

from parsers.base import BaseParser

logger = logging.getLogger(__name__)

_COMMON_WINDOWS_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]


class TesseractParser(BaseParser):
    """Parse scanned / non-born-digital PDF documents using Tesseract OCR."""

    name = "tesseract"

    def __init__(
        self,
        lang: str = "ara+eng",
        dpi: int = 300,
        psm: int | None = None,
        paddle_fallback: bool = True,
        paddle_threshold: float = 60.0,
        tesseract_cmd: Optional[str] = None,
    ) -> None:
        self.lang = lang
        self.dpi = dpi
        self.psm = psm
        self.paddle_fallback = paddle_fallback
        self.paddle_threshold = paddle_threshold
        self.last_ocr_profile: dict[str, int | float | str] = {}
        self._paddle = None

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        else:
            for candidate in _COMMON_WINDOWS_PATHS:
                if os.path.exists(candidate):
                    pytesseract.pytesseract.tesseract_cmd = candidate
                    break

    def _choose_psm(self, document: fitz.Document) -> int:
        """Choose the page segmentation mode from representative text pages.

        ``PSM 6`` assumes one uniform block and is often poor for textbook
        pages.  ``PSM 3`` lets Tesseract discover the layout.  Sampling three
        interior pages is inexpensive compared with OCR'ing a whole book and
        avoids requiring a user-facing OCR setting.
        """
        if self.psm is not None:
            self.last_ocr_profile = {"psm": self.psm, "selection": "configured"}
            return self.psm

        sample_indexes = sorted({
            max(0, len(document) // 4),
            max(0, len(document) // 2),
            max(0, (3 * len(document)) // 4),
        })
        scores: dict[int, list[float]] = {3: [], 6: []}
        for page_index in sample_indexes:
            page = document[page_index]
            pix = page.get_pixmap(dpi=180, alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
            for candidate in scores:
                try:
                    data = pytesseract.image_to_data(
                        image,
                        lang=self.lang,
                        config=f"--oem 3 --psm {candidate}",
                        output_type=Output.DICT,
                    )
                    confidences = [
                        float(confidence)
                        for text, confidence in zip(data["text"], data["conf"])
                        if str(text).strip() and float(confidence) >= 0
                    ]
                    if len(confidences) >= 8:
                        scores[candidate].append(sum(confidences) / len(confidences))
                except Exception:
                    continue

        averages = {
            candidate: (sum(values) / len(values) if values else 0.0)
            for candidate, values in scores.items()
        }
        selected = max(averages, key=averages.get)
        self.last_ocr_profile = {
            "psm": selected,
            "selection": "sampled",
            "psm_3_mean": round(averages[3], 2),
            "psm_6_mean": round(averages[6], 2),
        }
        return selected

    def _try_paddle(self, image: Image.Image, language: str) -> tuple[str, float] | None:
        """Return an improved result only when optional PaddleOCR is available."""
        if not self.paddle_fallback:
            return None
        try:
            if self._paddle is None:
                from parsers.paddle_ocr import PaddleOCRFallback
                self._paddle = PaddleOCRFallback(language)
            return self._paddle.extract(image)
        except Exception as exc:
            # Missing optional dependencies and an unavailable GPU must not turn
            # a recoverable OCR page into a failed document.
            logger.info("PaddleOCR fallback unavailable: %s", exc)
            self.paddle_fallback = False
            return None

    def parse(self, file_path: str) -> str:
        """Perform OCR on PDF pages and return extracted text.

        Args:
            file_path: Path to the input PDF document.

        Returns:
            Extracted text string.
        """
        try:
            pytesseract.get_tesseract_version()
        except Exception as exc:
            # Fallback to PyMuPDF text layer extraction if Tesseract binary is not installed
            doc = fitz.open(file_path)
            extracted = []
            for page_num, page in enumerate(doc, 1):
                text = page.get_text().strip()
                if text:
                    extracted.append(f"<!-- page: {page_num} -->\n{text}")
            doc.close()
            if extracted:
                return "\n\n".join(extracted)
            raise RuntimeError(
                "Tesseract binary is not installed on system PATH. "
                "Download from https://github.com/UB-Mannheim/tesseract/wiki "
                "or install tesseract-ocr via apt/brew."
            ) from exc

        requested_languages = set(self.lang.split("+"))
        installed_languages = set(pytesseract.get_languages(config=""))
        missing_languages = sorted(requested_languages - installed_languages)
        if missing_languages:
            raise RuntimeError(
                "Required Tesseract language data is missing: "
                f"{', '.join(missing_languages)}. Install the matching traineddata "
                "files (for example: apt install tesseract-ocr-ara) and rerun."
            )

        doc = fitz.open(file_path)
        full_text = []
        try:
            selected_psm = self._choose_psm(doc)
            paddle_pages = 0
            ocr_language = "ar" if "ara" in requested_languages and "eng" not in requested_languages else "en"
            for page_num, page in enumerate(doc, 1):
                pix = page.get_pixmap(dpi=self.dpi)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                if img.mode != "L":
                    img = img.convert("L")

                try:
                    data = pytesseract.image_to_data(
                        img,
                        lang=self.lang,
                        config=f"--oem 3 --psm {selected_psm}",
                        output_type=Output.DICT,
                    )
                    words = []
                    confidences = []
                    for text, confidence in zip(data["text"], data["conf"]):
                        clean = text.strip()
                        try:
                            score = float(confidence)
                        except (TypeError, ValueError):
                            score = -1.0
                        if clean:
                            words.append(clean)
                            if score >= 0:
                                confidences.append(score)

                    page_text = " ".join(words)
                    mean_confidence = (
                        sum(confidences) / len(confidences) if confidences else 0.0
                    )
                    if mean_confidence < self.paddle_threshold:
                        paddle_result = self._try_paddle(img, ocr_language)
                        if paddle_result is not None:
                            paddle_text, paddle_confidence = paddle_result
                            # Never replace usable Tesseract text with a weaker
                            # second OCR result.  A small margin avoids flapping.
                            if paddle_text and paddle_confidence > mean_confidence + 2:
                                page_text, mean_confidence = paddle_text, paddle_confidence
                                paddle_pages += 1
                    full_text.append(
                        f"<!-- page: {page_num} -->\n"
                        f"<!-- ocr_confidence: {mean_confidence:.2f} -->\n"
                        f"{page_text}"
                    )
                except Exception as exc:
                    # Preserve page provenance even when a language pack is missing.
                    logger.warning("Tesseract OCR failed on page %s: %s", page_num, exc)
                    full_text.append(
                        f"<!-- page: {page_num} -->\n"
                        f"<!-- ocr_confidence: 0.00 -->\n{page.get_text().strip()}"
                    )
        finally:
            doc.close()
        self.last_ocr_profile["paddle_pages"] = paddle_pages
        return "\n\n".join(full_text)
