"""Regression tests for OCR page provenance and confidence propagation."""

from educational.rule_based_parser import parse_markdown_to_education
from evaluation.metrics import ocr_confidence_check


def test_ocr_confidence_marker_is_normalized_and_flagged():
    document = parse_markdown_to_education(
        "<!-- page: 4 -->\n<!-- ocr_confidence: 55.0 -->\nUncertain OCR text.",
        "scan.pdf",
        "tesseract",
        "en",
    )
    element = document.all_elements()[0][0]

    assert element.metadata.page == 4
    assert element.metadata.confidence == 0.55
    assert element.metadata.extra["needs_review"] is True
    assert ocr_confidence_check(document)["status"] == "FAIL"


def test_high_confidence_ocr_passes():
    document = parse_markdown_to_education(
        "<!-- page: 1 -->\n<!-- ocr_confidence: 92.5 -->\nClear OCR text.",
        "scan.pdf",
        "tesseract",
        "en",
    )
    assert ocr_confidence_check(document)["status"] == "PASS"
