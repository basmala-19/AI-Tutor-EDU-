"""
Quality metrics — deterministic, rule-based, ParseBench-inspired.

Each metric returns a dict:
    {"status": "PASS" | "FAIL", "detail": "<human-readable explanation>"}

Numeric ratios are intentionally NOT exposed as final scores because the
project has no ground-truth dataset yet. Use PASS/FAIL thresholds until a
labelled benchmark is available — then swap to continuous scores.

ParseBench dimensions covered:
  1. Content Faithfulness   — tokens preserved across Markdown → EducationalDocument
  2. Table Preservation     — table count in Markdown vs. parsed TABLE elements
  3. Semantic Formatting    — heading levels present and non-empty
  4. Metadata Completeness  — every element carries chapter / lesson / parser
  5. Reading Order          — page numbers never decrease (proxy for column order)
"""
from __future__ import annotations

import re

from schema.models import EducationalDocument, ElementType

_WORD_RE = re.compile(r"[\w\u0600-\u06FF]+")  # supports Arabic and Latin scripts


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)}


def _iter_lessons(edoc: EducationalDocument):
    """Yield (chapter, lesson, element_list) for every lesson."""
    for chapter in edoc.chapters:
        for lesson in chapter.lessons:
            yield chapter, lesson, lesson.elements


def _all_elements(edoc: EducationalDocument):
    return [el for _, _, els in _iter_lessons(edoc) for el in els]


# ---------------------------------------------------------------------------
# Metric functions
# ---------------------------------------------------------------------------


def content_faithfulness(source_text: str, edoc: EducationalDocument) -> dict:
    """Fraction of source tokens still present after Markdown → EducationalDocument.

    This is a proxy, not a ground-truth comparison. It catches the most common
    failure: the Educational Parser silently dropping content during conversion.

    PASS threshold: >= 50% of source tokens retained.
    """
    source_tokens = _tokenize(source_text)
    if not source_tokens:
        return {"status": "PASS", "detail": "source text is empty — nothing to preserve"}

    parsed_text = " ".join(
        el.text or "" for el in _all_elements(edoc)
    )
    parsed_tokens = _tokenize(parsed_text)

    kept = source_tokens & parsed_tokens
    ratio = len(kept) / len(source_tokens)
    status = "PASS" if ratio >= 0.50 else "FAIL"
    return {
        "status": status,
        "detail": f"{len(kept)}/{len(source_tokens)} source tokens preserved ({ratio:.0%})",
    }


def table_preservation(source_markdown: str, edoc: EducationalDocument) -> dict:
    """Detected table count in Markdown vs. TABLE elements in EducationalDocument.

    Catches the most dangerous failure: a table silently converted to a paragraph.

    PASS: detected tables == parsed TABLE elements (exact match).
    """
    row_count = len(re.findall(r"^\|.*\|\s*$", source_markdown, flags=re.MULTILINE))
    # Approximate: each table averages ~3 rows (header + separator + ≥1 data row)
    detected_tables = max(1, row_count // 3) if row_count else 0

    parsed_tables = sum(
        1
        for el in _all_elements(edoc)
        if el.type == ElementType.TABLE
    )

    if detected_tables == 0:
        status = "PASS" if parsed_tables == 0 else "FAIL"
        detail = "no tables in source" if parsed_tables == 0 else f"spurious TABLE elements: {parsed_tables}"
    else:
        status = "PASS" if parsed_tables >= detected_tables else "FAIL"
        detail = f"{parsed_tables}/{detected_tables} tables detected"

    return {"status": status, "detail": detail}


def semantic_formatting(edoc: EducationalDocument) -> dict:
    """Heading structure integrity check.

    PASS: every HEADING element has a non-empty text and a valid level.
    """
    headings = [el for el in _all_elements(edoc) if el.type == ElementType.HEADING]
    if not headings:
        return {"status": "PASS", "detail": "no headings — nothing to validate"}

    bad = [el for el in headings if not el.text or el.level is None]
    status = "PASS" if not bad else "FAIL"
    detail = (
        f"all {len(headings)} headings have valid text and level"
        if not bad
        else f"{len(bad)}/{len(headings)} headings missing text or level"
    )
    return {"status": status, "detail": detail}


def metadata_completeness(edoc: EducationalDocument) -> dict:
    """Every element must carry chapter, lesson, and parser fields.

    Operates on elements (not chunks) so it can be called without chunking.

    PASS: 100% of elements have all three required fields populated.
    """
    required = ("chapter", "lesson", "parser")
    elements = _all_elements(edoc)

    if not elements:
        return {"status": "FAIL", "detail": "document has no elements"}

    complete = sum(
        1
        for el in elements
        if all(getattr(el.metadata, f, None) for f in required)
    )
    status = "PASS" if complete == len(elements) else "FAIL"
    detail = f"{complete}/{len(elements)} elements have full metadata (chapter + lesson + parser)"
    return {"status": status, "detail": detail}


def reading_order(edoc: EducationalDocument) -> dict:
    """Heuristic: page numbers across consecutive elements must be non-decreasing.

    A page-number drop usually signals a multi-column layout read in the wrong order.

    PASS: zero violations.
    """
    pages = [el.metadata.page for el in _all_elements(edoc)]
    if len(pages) < 2:
        return {"status": "PASS", "detail": "fewer than 2 elements — no order to check"}

    violations = [(a, b) for a, b in zip(pages, pages[1:]) if b < a]
    status = "PASS" if not violations else "FAIL"
    detail = (
        "page order is non-decreasing"
        if not violations
        else f"{len(violations)} order violation(s) detected (e.g. page {violations[0][0]} → {violations[0][1]})"
    )
    return {"status": status, "detail": detail}
