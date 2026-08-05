"""
Tesseract OCR Parser — supports Arabic ('ara'), English ('eng'), and mixed document OCR.

Requires Tesseract binary installed on the OS:
  - Windows: https://github.com/UB-Mannheim/tesseract/wiki
  - Linux:   sudo apt install tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng
  - Mac:     brew install tesseract tesseract-lang
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Optional

import fitz
from PIL import Image
import pytesseract
from pytesseract import Output

from parsers.base import BaseParser

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
        psm: int = 6,
        tesseract_cmd: Optional[str] = None,
    ) -> None:
        self.lang = lang
        self.dpi = dpi
        self.psm = psm

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        else:
            for candidate in _COMMON_WINDOWS_PATHS:
                if os.path.exists(candidate):
                    pytesseract.pytesseract.tesseract_cmd = candidate
                    break

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

        doc = fitz.open(file_path)
        full_text = []
        try:
            for page_num, page in enumerate(doc, 1):
                pix = page.get_pixmap(dpi=self.dpi)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                if img.mode != "L":
                    img = img.convert("L")

                try:
                    data = pytesseract.image_to_data(
                        img,
                        lang=self.lang,
                        config=f"--psm {self.psm}",
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
                    full_text.append(
                        f"<!-- page: {page_num} -->\n"
                        f"<!-- ocr_confidence: {mean_confidence:.2f} -->\n"
                        f"{page_text}"
                    )
                except Exception:
                    # Preserve page provenance even when a language pack is missing.
                    full_text.append(f"<!-- page: {page_num} -->\n{page.get_text().strip()}")
        finally:
            doc.close()
        return "\n\n".join(full_text)
