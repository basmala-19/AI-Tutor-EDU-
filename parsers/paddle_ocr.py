"""Optional, selective PaddleOCR fallback for weak Tesseract pages.

PaddleOCR is intentionally not a mandatory project dependency.  It downloads
models on first use and is only invoked for pages whose Tesseract confidence is
below the review threshold.  This keeps normal textbook ingestion lightweight.
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np
from PIL import Image


class PaddleOCRFallback:
    """Lazily load PaddleOCR and return text plus mean recognition confidence."""

    def __init__(self, language: str) -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR is optional and is not installed. Install the host-appropriate "
                "PaddlePaddle package, then run: pip install paddleocr"
            ) from exc

        # PP-OCRv5 has a dedicated Arabic recognizer.  English uses its compact
        # multilingual recognizer.  The flags avoid expensive document-wide
        # orientation/unwarping stages because this class receives one rendered
        # page only after Tesseract has flagged it.
        kwargs: dict[str, Any] = {
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        }
        if language == "ar":
            kwargs["text_recognition_model_name"] = "arabic_PP-OCRv5_mobile_rec"
        else:
            kwargs["text_recognition_model_name"] = "PP-OCRv5_mobile_rec"
        self._engine = PaddleOCR(**kwargs)

    def extract(self, image: Image.Image) -> tuple[str, float]:
        """Extract text in layout order across PaddleOCR v2/v3 result formats."""
        array = np.asarray(image.convert("RGB"))
        texts: list[str] = []
        scores: list[float] = []

        if hasattr(self._engine, "predict"):
            for prediction in self._engine.predict(array):
                payload = getattr(prediction, "json", prediction)
                payload = payload() if callable(payload) else payload
                if isinstance(payload, str):
                    payload = json.loads(payload)
                if not isinstance(payload, dict):
                    continue
                values = payload.get("res", payload)
                for text, score in zip(values.get("rec_texts", []), values.get("rec_scores", [])):
                    if str(text).strip():
                        texts.append(str(text).strip())
                        scores.append(float(score) * 100)
        else:  # Compatibility with PaddleOCR 2.x, useful on older notebooks.
            for page_result in self._engine.ocr(array, cls=False) or []:
                for line in page_result or []:
                    text, score = line[1]
                    if str(text).strip():
                        texts.append(str(text).strip())
                        scores.append(float(score) * 100)

        confidence = sum(scores) / len(scores) if scores else 0.0
        return " ".join(texts), confidence
