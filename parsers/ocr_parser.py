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
            for page in doc:
                text = page.get_text().strip()
                if text:
                    extracted.append(text)
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

        for page_num, page in enumerate(doc, 1):
            pix = page.get_pixmap(dpi=self.dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            if img.mode != "L":
                img = img.convert("L")

            try:
                text = pytesseract.image_to_string(
                    img,
                    lang=self.lang,
                    config=f"--psm {self.psm}",
                )
                full_text.append(text.strip())
            except Exception:
                # Fallback to page text if language pack is missing
                full_text.append(page.get_text().strip())

        doc.close()
        return "\n\n".join(full_text)
